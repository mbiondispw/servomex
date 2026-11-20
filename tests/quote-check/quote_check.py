#!/usr/bin/env python3
"""
Quote-check harness: prove, headlessly, that the org quotes products as specified.

Each scenario creates one real Quote in the target org through Place Sales
Transaction (the API the Revenue Cloud quote UI uses), lets the org configure and
price it, then checks the priced Quote Line Items against the scenario's
expectations. Scenarios live in YAML files under tests/quote-check/scenarios/,
so new behaviour is verified by adding a scenario, not by changing this script.

Usage:
    python tests/quote-check/quote_check.py --org <sf-alias> \
        [--scenarios tests/quote-check/scenarios/minimp-05230a1.yaml] [--only <name>]

Writes to the org: a test Account per scenario account key (reused across runs)
and one new Quote per scenario run. It never updates or deletes anything else.
Auth is delegated to the sf CLI, so --org is an sf alias or username.

Exit codes:
    0  every scenario passed
    1  a scenario failed, or the org rejected a request
    2  usage or scenario-file error
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    sys.stderr.write("error: PyYAML is required. Install it with: python -m pip install PyYAML\n")
    raise SystemExit(2)

API = "v66.0"
DEFAULT_SCENARIOS = Path(__file__).resolve().parent / "scenarios" / "minimp-05230a1.yaml"
CALCULATED = {"CompletedWithPricing", "CompletedWithTax", "CompletedWithoutPricing"}
POLL_SECONDS = 3
POLL_TIMEOUT = 180
MONEY_TOLERANCE = Decimal("0.005")
# A refusal containing one of these is the model failing, not a rule rejecting.
MODEL_FAILURE_MARKERS = ("INTERNAL_SERVER_ERROR", "Deploy failed", "is invalid")


class CheckError(RuntimeError):
    """The org refused a request, so the scenario cannot be judged."""


# ---------------------------------------------------------------------------
# sf CLI plumbing
# ---------------------------------------------------------------------------


def sf(args):
    result = subprocess.run(["sf", *args, "--json"], capture_output=True, text=True)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise CheckError(f"sf {' '.join(args[:3])}: {(result.stderr or result.stdout)[:400]}")
    if payload.get("status", 0) != 0:
        raise CheckError(f"sf {' '.join(args[:3])}: {payload.get('message', payload)}")
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
        raise CheckError(f"{method} {path}: unparseable response: {text[:400]}")


# ---------------------------------------------------------------------------
# Org fixtures
# ---------------------------------------------------------------------------


def ensure_account(org, spec):
    """Reuse the named test account, creating it on first use."""
    rows = query(org, f"SELECT Id, Type, CurrencyIsoCode FROM Account WHERE Name = {soql_literal(spec['name'])}")
    if len(rows) > 1:
        raise CheckError(f"more than one Account named '{spec['name']}'")
    if rows:
        account = rows[0]
        if account["Type"] != spec["type"] or account["CurrencyIsoCode"] != spec["currency"]:
            raise CheckError(
                f"Account '{spec['name']}' is Type {account['Type']} / {account['CurrencyIsoCode']}, "
                f"expected {spec['type']} / {spec['currency']}. Fix it by hand; the harness "
                "never edits an existing account."
            )
        return account["Id"]
    values = f"Name={soql_literal(spec['name'])} Type={soql_literal(spec['type'])} " \
             f"CurrencyIsoCode={soql_literal(spec['currency'])}"
    created = sf(["data", "create", "record", "--target-org", org, "--sobject", "Account", "--values", values])
    return created["id"]


def resolve_line(org, line, pricebook_id, currency):
    sku = line["sku"]
    products = query(org, f"SELECT Id FROM Product2 WHERE StockKeepingUnit = {soql_literal(sku)}")
    if len(products) != 1:
        raise CheckError(f"expected one Product2 with SKU {sku}, found {len(products)}")
    product_id = products[0]["Id"]
    entries = query(
        org,
        "SELECT Id, UnitPrice, ProductSellingModel.Name FROM PricebookEntry "
        f"WHERE Product2Id = '{product_id}' AND Pricebook2Id = '{pricebook_id}' "
        f"AND CurrencyIsoCode = {soql_literal(currency)} AND IsActive = true",
    )
    wanted = line.get("selling_model")
    if wanted:
        entries = [e for e in entries if (e.get("ProductSellingModel") or {}).get("Name") == wanted]
    if len(entries) != 1:
        raise CheckError(
            f"expected one active {currency} Standard Price Book entry for {sku}"
            + (f" with selling model {wanted}" if wanted else "")
            + f", found {len(entries)}. Set 'selling_model' on the line."
        )

    overrides = []
    for code, value in (line.get("attributes") or {}).items():
        definitions = query(
            org, f"SELECT Id, PicklistId FROM AttributeDefinition WHERE Code = {soql_literal(code)}"
        )
        if len(definitions) != 1:
            raise CheckError(f"no Attribute Definition with Code {code}")
        picklist_value_id = None
        if definitions[0]["PicklistId"]:
            # Place rejects a picklist override that names only its text value.
            picklist_values = query(
                org,
                "SELECT Id FROM AttributePicklistValue "
                f"WHERE PicklistId = '{definitions[0]['PicklistId']}' AND Value = {soql_literal(value)}",
            )
            if len(picklist_values) != 1:
                raise CheckError(f"{code} has no permitted value {value!r}")
            picklist_value_id = picklist_values[0]["Id"]
        overrides.append((definitions[0]["Id"], value, picklist_value_id))
    return product_id, entries[0], overrides


# ---------------------------------------------------------------------------
# Quote placement
# ---------------------------------------------------------------------------


def place_quote(org, scenario, account_id, currency):
    pricebook_id = query(org, "SELECT Id FROM Pricebook2 WHERE IsStandard = true")[0]["Id"]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    records = [{
        "referenceId": "refQuote",
        "record": {
            "attributes": {"type": "Quote", "method": "POST"},
            "Name": f"Quote Check: {scenario['name']} {stamp}"[:255],
            "QuoteAccountId": account_id,
            "Pricebook2Id": pricebook_id,
            "CurrencyIsoCode": currency,
        },
    }]
    for index, line in enumerate(scenario["lines"]):
        product_id, entry, overrides = resolve_line(org, line, pricebook_id, currency)
        line_ref = f"refLine{index}"
        records.append({
            "referenceId": line_ref,
            "record": {
                "attributes": {"type": "QuoteLineItem", "method": "POST"},
                "QuoteId": "@{refQuote.id}",
                "Product2Id": product_id,
                "PricebookEntryId": entry["Id"],
                "UnitPrice": entry["UnitPrice"],
                "Quantity": line.get("quantity", 1),
            },
        })
        for attr_index, (definition_id, value, picklist_value_id) in enumerate(overrides):
            record = {
                "attributes": {"type": "QuoteLineItemAttribute", "method": "POST"},
                "QuoteLineItemId": f"@{{{line_ref}.id}}",
                "AttributeDefinitionId": definition_id,
                "AttributeValue": value,
            }
            if picklist_value_id:
                record["AttributePicklistValueId"] = picklist_value_id
            records.append({"referenceId": f"{line_ref}Attr{attr_index}", "record": record})

    # Configure the way the quote UI does: apply product defaults, then run the
    # configuration rules, so the check sees what a rep would see.
    payload = {
        "pricingPref": "System",
        "configurationPref": {
            "configurationMethod": "System",
            "configurationOptions": {
                "validateProductCatalog": True,
                "validateAmendRenewCancel": False,
                "executeConfigurationRules": True,
                "addDefaultConfiguration": True,
            },
        },
        "graph": {"graphId": "quoteCheck", "records": records},
    }
    response = rest(org, "/connect/rev/sales-transaction/actions/place", "POST", payload)
    if isinstance(response, list):
        raise CheckError(f"place rejected: {response[0].get('message', response[0])}")
    errors = response.get("errorResponse") or []
    if errors or response.get("isSuccess") is False:
        detail = "; ".join(f"{e.get('referenceId', '?')}: {e.get('message', e)}" for e in errors)
        raise CheckError(f"place failed: {detail or json.dumps(response)[:400]}")
    quote_id = response.get("salesTransactionId")
    if not quote_id:
        raise CheckError(f"place returned no quote id: {json.dumps(response)[:400]}")
    return quote_id


def wait_until_calculated(org, quote_id):
    deadline = time.time() + POLL_TIMEOUT
    status = None
    while time.time() < deadline:
        status = query(org, f"SELECT CalculationStatus FROM Quote WHERE Id = '{quote_id}'")[0]["CalculationStatus"]
        if status in CALCULATED:
            return status
        if status and status.endswith("Failed"):
            raise CheckError(f"quote {quote_id} calculation status {status}")
        time.sleep(POLL_SECONDS)
    raise CheckError(f"quote {quote_id} still {status} after {POLL_TIMEOUT}s")


# ---------------------------------------------------------------------------
# Expectations
# ---------------------------------------------------------------------------


def priced_lines(org, quote_id, fields):
    columns = sorted({"Id", "Product2.StockKeepingUnit", *fields})
    lines = query(org, f"SELECT {', '.join(columns)} FROM QuoteLineItem WHERE QuoteId = '{quote_id}' ORDER BY CreatedDate")
    attributes = query(
        org,
        "SELECT QuoteLineItemId, AttributeDefinition.Code, AttributeValue FROM QuoteLineItemAttribute "
        f"WHERE QuoteLineItem.QuoteId = '{quote_id}'",
    )
    by_line = {}
    for row in attributes:
        by_line.setdefault(row["QuoteLineItemId"], {})[row["AttributeDefinition"]["Code"]] = row["AttributeValue"]
    for line in lines:
        line["attributes"] = by_line.get(line["Id"], {})
    return lines


def same_value(actual, expected):
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return actual is not None and abs(Decimal(str(actual)) - Decimal(str(expected))) <= MONEY_TOLERANCE
    return actual == expected


def check(scenario, lines):
    """Return a list of (passed, description) results for the scenario's expectations."""
    results = []
    for index, expected in enumerate(scenario["expect"]["lines"]):
        sku = expected["sku"]
        matching = [line for line in lines if line["Product2"]["StockKeepingUnit"] == sku]
        if not matching:
            results.append((False, f"line {index + 1}: no {sku} line on the quote"))
            continue
        line = matching[0]
        for field, value in (expected.get("fields") or {}).items():
            actual = line.get(field)
            results.append((same_value(actual, value), f"{sku} {field} = {value} (got {actual})"))
        for code, value in (expected.get("attributes") or {}).items():
            actual = line["attributes"].get(code)
            results.append((actual == value, f"{sku} {code} = {value!r} (got {actual!r})"))
    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def load_scenarios(path):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    accounts = data.get("accounts") or {}
    for scenario in data.get("scenarios") or []:
        for key in ("name", "account", "lines", "expect"):
            if key not in scenario:
                raise SystemExit(f"error: {path}: scenario {scenario.get('name', '?')} has no '{key}'")
        if scenario["account"] not in accounts:
            raise SystemExit(f"error: {path}: scenario {scenario['name']} names unknown account '{scenario['account']}'")
        expect = scenario["expect"] or {}
        if ("lines" in expect) == ("rejected" in expect):
            raise SystemExit(f"error: {path}: scenario {scenario['name']} expect needs exactly one of 'lines' or 'rejected'")
        if "rejected" in expect and expect["rejected"] is None:
            expect["rejected"] = {}
    return accounts, data.get("scenarios") or []


def configurator_refusal(org, quote_id):
    """Run the configuration rules on each line of a placed quote. Return the
    configurator's error messages joined, or None when every line solves cleanly."""
    refusals = []
    for line in query(org, f"SELECT Id FROM QuoteLineItem WHERE QuoteId = '{quote_id}'"):
        response = rest(org, "/connect/cpq/configurator/actions/configure", "POST", {
            "transactionId": quote_id,
            "transactionLineId": line["Id"],
            "correlationId": f"quote-check-{line['Id']}-{int(time.time())}",
            "configuratorOptions": {"executeConfigurationRules": True, "validateProductCatalog": True},
        })
        if isinstance(response, list):
            raise CheckError(f"configure rejected: {response[0].get('message', response[0])}")
        messages = [
            m.get("message", "")
            for entries in (response.get("messages") or {}).values()
            for m in entries
            if m.get("messageType") == "error"
        ]
        messages += [str(e.get("message", e)) for e in response.get("errors") or []]
        if response.get("solverStatus") == "error" or messages:
            refusals.append("; ".join(messages) or "solverStatus error")
    return " | ".join(refusals) if refusals else None


def check_rejected(scenario, refusal, lines):
    """A rejected scenario passes when the org refuses the configuration (with the
    expected message, if one is given), or, when no message is required, accepts the
    quote but does not keep the requested combination of attribute values."""
    message = scenario["expect"]["rejected"].get("message")
    if refusal is not None and any(marker in refusal for marker in MODEL_FAILURE_MARKERS):
        return [(False, f"configuration rules failed to run, so nothing was judged: {refusal}")]
    if refusal is not None:
        if message is None:
            return [(True, f"org refused the configuration: {refusal}")]
        return [(message in refusal, f"refusal says {message!r} (got {refusal!r})")]
    if message is not None:
        return [(False, f"org accepted the configuration; expected refusal saying {message!r}")]
    dropped = []
    for index, requested in enumerate(scenario["lines"]):
        matching = [line for line in lines if line["Product2"]["StockKeepingUnit"] == requested["sku"]]
        actual = matching[0]["attributes"] if matching else {}
        dropped += [
            f"{code} = {actual.get(code)!r} (requested {value!r})"
            for code, value in (requested.get("attributes") or {}).items()
            if actual.get(code) != value
        ]
    if dropped:
        return [(True, "requested combination not kept: " + "; ".join(dropped))]
    return [(False, "org accepted and kept the requested combination")]


def run_scenario(org, scenario, accounts):
    account = accounts[scenario["account"]]
    account_id = ensure_account(org, account)
    if "rejected" in scenario["expect"]:
        try:
            quote_id = place_quote(org, scenario, account_id, account["currency"])
            status = wait_until_calculated(org, quote_id)
        except CheckError as exc:
            return None, "refused", check_rejected(scenario, str(exc), [])
        # Place keeps a conflicted configuration; the configurator reports the conflict.
        refusal = configurator_refusal(org, quote_id)
        return quote_id, status, check_rejected(scenario, refusal, priced_lines(org, quote_id, set()))
    quote_id = place_quote(org, scenario, account_id, account["currency"])
    status = wait_until_calculated(org, quote_id)
    fields = {field for line in scenario["expect"]["lines"] for field in (line.get("fields") or {})}
    return quote_id, status, check(scenario, priced_lines(org, quote_id, fields))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check that the org quotes products as specified.")
    parser.add_argument("--org", required=True, help="sf CLI alias or username of the target org")
    parser.add_argument("--scenarios", default=DEFAULT_SCENARIOS, type=Path)
    parser.add_argument("--only", help="run only the scenario with this name")
    args = parser.parse_args(argv)

    accounts, scenarios = load_scenarios(args.scenarios)
    if args.only:
        scenarios = [s for s in scenarios if s["name"] == args.only]
        if not scenarios:
            parser.error(f"no scenario named '{args.only}'")

    failed = 0
    for scenario in scenarios:
        print(f"Scenario: {scenario['name']}")
        try:
            quote_id, status, results = run_scenario(args.org, scenario, accounts)
        except CheckError as exc:
            print(f"  ERROR {exc}")
            failed += 1
            continue
        print(f"  quote {quote_id} ({status})" if quote_id else f"  no quote ({status})")
        for passed, description in results:
            print(f"  {'ok  ' if passed else 'FAIL'} {description}")
        if not results or not all(passed for passed, _ in results):
            failed += 1
    print(f"\n{len(scenarios) - failed} of {len(scenarios)} scenarios passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
