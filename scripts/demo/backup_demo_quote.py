#!/usr/bin/env python3
"""
Backup demo quote: a send-ready Quote on NordicGas AS for the Send Proposal act.

Ensures, in the target org:
  1. Lars Eriksson (the NordicGas AS Quote Contact) holds a Demo Inbox Address.
     If not, it stops: run the contact email rewrite first.
  2. The backup Opportunity on NordicGas AS exists (created when missing).
  3. The backup Quote exists on it, with Lars Eriksson as Quote Contact and
     priced by the pricing engine. It's created through Place Sales Transaction,
     the API the Revenue Cloud quote UI uses.
  4. On later runs, the same Quote is reused and reset to Draft. Earlier
     Proposal Files and logged emails stay on it, because nothing is deleted.

Usage:
    python scripts/demo/backup_demo_quote.py --org <sf-alias-or-username> [--dry-run]

--dry-run only reads the org and prints what a real run would do.
Auth is delegated to the sf CLI, so --org is an sf alias or username, not a
CCI alias. The CCI task `create_backup_demo_quote` passes the org username.

Exit codes:
    0  the backup Quote is ready (or, with --dry-run, a real run would succeed)
    1  a precondition failed or the org rejected a request
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import date, timedelta

API = "v66.0"
ACCOUNT_NAME = "NordicGas AS"
CONTACT_FIRST_NAME = "Lars"
CONTACT_LAST_NAME = "Eriksson"
OPPORTUNITY_NAME = "NordicGas AS — Analyser Upgrade (Backup Demo)"
QUOTE_NAME = "NordicGas AS — Backup Demo Quote"
OPPORTUNITY_STAGE = "Proposal/Quote"
VALIDITY_DAYS = 30
# Simple analysers and spares that price cleanly in USD (the Quote Account's
# currency). Keep the SERVOFLEX Mini MP out: its model changes often.
LINES = [
    ("SMX-4900-MG", 1),   # SERVOPRO 4900 Multigas Analyser
    ("SMX-SPA-CALG", 2),  # Calibration Gas Kit (12-month)
]
DEMO_INBOX_CHECK_ACTION = "/actions/custom/apex/DemoInboxAddress"
CALCULATED = {"CompletedWithPricing", "CompletedWithTax", "CompletedWithoutPricing"}
POLL_SECONDS = 3
POLL_TIMEOUT = 180


class BackupQuoteError(RuntimeError):
    """A precondition failed or the org refused a request."""


# ---------------------------------------------------------------------------
# sf CLI plumbing
# ---------------------------------------------------------------------------


def sf(args):
    result = subprocess.run(["sf", *args, "--json"], capture_output=True, text=True)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise BackupQuoteError(f"sf {' '.join(args[:3])}: {(result.stderr or result.stdout)[:400]}")
    if payload.get("status", 0) != 0:
        raise BackupQuoteError(f"sf {' '.join(args[:3])}: {payload.get('message', payload)}")
    return payload["result"]


def soql_literal(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def query(org, soql):
    return sf(["data", "query", "--target-org", org, "--query", soql])["records"]


def rest(org, path, method="GET", body=None):
    args = ["api", "request", "rest", f"/services/data/{API}{path}",
            "--target-org", org, "--method", method]
    if body is not None:
        args += ["--body", json.dumps(body)]
    result = subprocess.run(["sf", *args], capture_output=True, text=True)
    text = result.stdout.strip() or result.stderr.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        raise BackupQuoteError(f"{method} {path}: unparseable response: {text[:400]}")


def values_arg(fields):
    return " ".join(f"{name}={soql_literal(value)}" for name, value in fields.items())


def create_record(org, sobject, fields):
    return sf(["data", "create", "record", "--target-org", org, "--sobject", sobject,
               "--values", values_arg(fields)])["id"]


def update_record(org, sobject, record_id, fields):
    sf(["data", "update", "record", "--target-org", org, "--sobject", sobject,
        "--record-id", record_id, "--values", values_arg(fields)])


def one_or_none(rows, what):
    if len(rows) > 1:
        raise BackupQuoteError(f"found {len(rows)} {what}; expected at most one. Remove the extras by hand.")
    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Org state
# ---------------------------------------------------------------------------


def demo_inbox_problem(org, contact):
    """Ask the org's Demo Inbox Address check, so the rule lives in one place.

    Returns None when the Quote Contact's email is a Demo Inbox Address, else
    the reason the run must stop.
    """
    email = contact["Email"] or ""
    response = rest(org, DEMO_INBOX_CHECK_ACTION, "POST", {"inputs": [{"emailAddress": email}]})
    result = response[0] if isinstance(response, list) and response else {}
    if not result.get("isSuccess"):
        return (
            "the org's Demo Inbox Address check isn't available. Deploy the contact email rewrite "
            f"and run it first. Detail: {json.dumps(result.get('errors') or response)[:300]}"
        )
    if not result["outputValues"]["isDemoInboxAddress"]:
        return (
            f"{CONTACT_FIRST_NAME} {CONTACT_LAST_NAME}'s email ({email or 'blank'}) is not a Demo Inbox "
            "Address. Run the contact email rewrite task first, then re-run this task."
        )
    return None


def read_state(org):
    """Everything a run needs, read without writing anything."""
    account = one_or_none(
        query(org, f"SELECT Id, CurrencyIsoCode FROM Account WHERE Name = {soql_literal(ACCOUNT_NAME)}"),
        f"Accounts named {ACCOUNT_NAME}",
    )
    if not account:
        raise BackupQuoteError(f"no Account named {ACCOUNT_NAME}")
    contact = one_or_none(
        query(org, "SELECT Id, Email FROM Contact "
                   f"WHERE AccountId = '{account['Id']}' AND FirstName = {soql_literal(CONTACT_FIRST_NAME)} "
                   f"AND LastName = {soql_literal(CONTACT_LAST_NAME)}"),
        f"Contacts named {CONTACT_FIRST_NAME} {CONTACT_LAST_NAME} on {ACCOUNT_NAME}",
    )
    if not contact:
        raise BackupQuoteError(f"no Contact {CONTACT_FIRST_NAME} {CONTACT_LAST_NAME} on {ACCOUNT_NAME}")

    pricebook_id = query(org, "SELECT Id FROM Pricebook2 WHERE IsStandard = true")[0]["Id"]
    currency = account["CurrencyIsoCode"]
    lines = []
    for code, quantity in LINES:
        entries = query(
            org,
            "SELECT Id, Product2Id, Product2.Name, UnitPrice FROM PricebookEntry "
            f"WHERE Product2.ProductCode = {soql_literal(code)} AND Product2.IsActive = true "
            f"AND Pricebook2Id = '{pricebook_id}' AND CurrencyIsoCode = {soql_literal(currency)} "
            "AND IsActive = true",
        )
        if len(entries) != 1:
            raise BackupQuoteError(
                f"expected one active {currency} Standard Price Book entry for product {code}, found {len(entries)}"
            )
        lines.append((entries[0], quantity))

    opportunity = one_or_none(
        query(org, "SELECT Id FROM Opportunity "
                   f"WHERE AccountId = '{account['Id']}' AND Name = {soql_literal(OPPORTUNITY_NAME)}"),
        f"Opportunities named {OPPORTUNITY_NAME}",
    )
    quote = None
    if opportunity:
        quote = one_or_none(
            query(org, "SELECT Id, QuoteNumber, Status, ContactId, ExpirationDate FROM Quote "
                       f"WHERE OpportunityId = '{opportunity['Id']}' AND Name = {soql_literal(QUOTE_NAME)}"),
            f"Quotes named {QUOTE_NAME}",
        )
    return {
        "account": account, "contact": contact, "pricebook_id": pricebook_id,
        "currency": currency, "lines": lines, "opportunity": opportunity, "quote": quote,
        "inbox_problem": demo_inbox_problem(org, contact),
    }


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def create_opportunity(org, state):
    return create_record(org, "Opportunity", {
        "Name": OPPORTUNITY_NAME,
        "AccountId": state["account"]["Id"],
        "StageName": OPPORTUNITY_STAGE,
        "CloseDate": (date.today() + timedelta(days=90)).isoformat(),
        "CurrencyIsoCode": state["currency"],
        "Pricebook2Id": state["pricebook_id"],
    })


def place_quote(org, state, opportunity_id):
    records = [{
        "referenceId": "refQuote",
        "record": {
            "attributes": {"type": "Quote", "method": "POST"},
            "Name": QUOTE_NAME,
            "OpportunityId": opportunity_id,
            "QuoteAccountId": state["account"]["Id"],
            "ContactId": state["contact"]["Id"],
            "Pricebook2Id": state["pricebook_id"],
            "CurrencyIsoCode": state["currency"],
            "Status": "Draft",
            "ExpirationDate": (date.today() + timedelta(days=VALIDITY_DAYS)).isoformat(),
        },
    }]
    for index, (entry, quantity) in enumerate(state["lines"]):
        records.append({
            "referenceId": f"refLine{index}",
            "record": {
                "attributes": {"type": "QuoteLineItem", "method": "POST"},
                "QuoteId": "@{refQuote.id}",
                "Product2Id": entry["Product2Id"],
                "PricebookEntryId": entry["Id"],
                "UnitPrice": entry["UnitPrice"],
                "Quantity": quantity,
            },
        })
    payload = {"pricingPref": "System", "graph": {"graphId": "backupDemoQuote", "records": records}}
    response = rest(org, "/connect/rev/sales-transaction/actions/place", "POST", payload)
    if isinstance(response, list):
        raise BackupQuoteError(f"place rejected: {response[0].get('message', response[0])}")
    errors = response.get("errorResponse") or []
    if errors or response.get("isSuccess") is False:
        detail = "; ".join(f"{e.get('referenceId', '?')}: {e.get('message', e)}" for e in errors)
        raise BackupQuoteError(f"place failed: {detail or json.dumps(response)[:400]}")
    quote_id = response.get("salesTransactionId")
    if not quote_id:
        raise BackupQuoteError(f"place returned no quote id: {json.dumps(response)[:400]}")
    return quote_id


def wait_until_calculated(org, quote_id):
    deadline = time.time() + POLL_TIMEOUT
    status = None
    while time.time() < deadline:
        status = query(org, f"SELECT CalculationStatus FROM Quote WHERE Id = '{quote_id}'")[0]["CalculationStatus"]
        if status in CALCULATED:
            return status
        if status and status.endswith(("Failed", "Incomplete")):
            raise BackupQuoteError(f"quote {quote_id} calculation status {status}")
        time.sleep(POLL_SECONDS)
    raise BackupQuoteError(f"quote {quote_id} still {status} after {POLL_TIMEOUT}s")


def reset_fields(state):
    """The fields to change so a reused backup Quote is send-ready again."""
    quote = state["quote"]
    fields = {}
    if quote["Status"] != "Draft":
        fields["Status"] = "Draft"
    if quote["ContactId"] != state["contact"]["Id"]:
        fields["ContactId"] = state["contact"]["Id"]
    if not quote["ExpirationDate"] or quote["ExpirationDate"] < date.today().isoformat():
        fields["ExpirationDate"] = (date.today() + timedelta(days=VALIDITY_DAYS)).isoformat()
    return fields


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(org, dry_run=False, log=print):
    state = read_state(org)
    prefix = "Would " if dry_run else ""
    contact = f"{CONTACT_FIRST_NAME} {CONTACT_LAST_NAME} <{state['contact']['Email']}>"
    if state["inbox_problem"] and not dry_run:
        raise BackupQuoteError(state["inbox_problem"])
    log(f"Quote Contact: {contact} "
        + ("(NOT a Demo Inbox Address: a real run stops here)" if state["inbox_problem"] else "(Demo Inbox Address)"))

    opportunity_id = (state["opportunity"] or {}).get("Id")
    if opportunity_id:
        log(f"Opportunity: reusing {OPPORTUNITY_NAME} ({opportunity_id})")
    else:
        log(f"{prefix}create Opportunity {OPPORTUNITY_NAME} on {ACCOUNT_NAME}")
        if not dry_run:
            opportunity_id = create_opportunity(org, state)

    quote = state["quote"]
    if quote:
        fields = reset_fields(state)
        changes = ", ".join(f"{k}={v}" for k, v in fields.items()) or "nothing to change"
        log(f"Quote: reusing {quote['QuoteNumber']} ({quote['Id']}); {prefix.lower()}reset: {changes}")
        if fields and not dry_run:
            update_record(org, "Quote", quote["Id"], fields)
        quote_id = quote["Id"]
    else:
        summary = ", ".join(f"{qty} x {entry['Product2']['Name']}" for entry, qty in state["lines"])
        log(f"{prefix}create Quote {QUOTE_NAME} via Place Sales Transaction: {summary}")
        quote_id = None
        if not dry_run:
            quote_id = place_quote(org, state, opportunity_id)
            log(f"  calculation: {wait_until_calculated(org, quote_id)}")

    if dry_run:
        if state["inbox_problem"]:
            raise BackupQuoteError(state["inbox_problem"])
        return quote_id
    final = query(org, "SELECT QuoteNumber, Status, GrandTotal, CurrencyIsoCode, LineItemCount, Contact.Email "
                       f"FROM Quote WHERE Id = '{quote_id}'")[0]
    if not final["LineItemCount"] or not final["GrandTotal"]:
        raise BackupQuoteError(
            f"backup Quote {final['QuoteNumber']} ({quote_id}) has {final['LineItemCount']} lines and grand "
            f"total {final['GrandTotal']}. Delete it by hand and re-run to rebuild it."
        )
    log(f"Backup Quote ready: {final['QuoteNumber']} ({quote_id}) {final['Status']}, "
        f"{final['CurrencyIsoCode']} {final['GrandTotal']:,.2f} over {final['LineItemCount']} lines, "
        f"Quote Contact {final['Contact']['Email']}")
    return quote_id


def main(argv=None):
    parser = argparse.ArgumentParser(description="Create or reset the NordicGas AS backup demo quote.")
    parser.add_argument("--org", required=True, help="sf CLI alias or username of the target org")
    parser.add_argument("--dry-run", action="store_true", help="read the org and print the plan; write nothing")
    args = parser.parse_args(argv)
    try:
        run(args.org, args.dry_run)
    except BackupQuoteError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
