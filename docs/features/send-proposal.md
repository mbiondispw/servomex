# Send Proposal — Feature Documentation

> **Deploy:** `cci flow run deploy_send_proposal --org servomex`
> **Source:** `force-app/main/default/` (flow, quick action, email template, flexipage)

---

## Overview

**Send Proposal** is a Quote action that emails the **Proposal** to the
**Quote Contact** and marks the Quote **Presented**, in one step. It works for
every Quote Account type; there's no Partner rule and no approval gate.

| Piece | Metadata |
|-------|----------|
| Screen flow | `flows/Servomex_Send_Proposal` |
| Quote action, label "Send Proposal" | `quickActions/Quote.Servomex_Send_Proposal` |
| Email template, related to Quote, recipient Contact | `email/Servomex/Servomex_Proposal` (folder `Servomex`) |
| Quote record page with the action | `flexipages/Servomex_Quote_Record_Page` |
| Page assignment task | `assign_servomex_quote_page` (`tasks/servomex_record_page.py`) |

## What the action does

1. **Entry checks** run before any screen. Each failure shows its own message
   and stops without changing anything:
   - Status is **Accepted** or **Denied**.
   - The Quote has no **Quote Contact** (the Quote's Contact field).
   - The Quote Contact's email isn't a **Demo Inbox Address**. The message tells
     the operator to run `cci task run rewrite_contact_emails_to_demo_inbox --org servomex`.
   - The `Servomex_Proposal` email template is missing.
2. **Confirmation screen.** It shows the Quote Contact's name and email, and a
   picker of the active Revenue Lifecycle Management document templates,
   defaulting to `RLM_QuoteProposal_CS`. There's no editable email content.
   **Send** continues; closing the window cancels.
3. **Generation.**
   - The flow calls rlm-base-dev's `RLM_DocumentGenerationCreate`. The Proposal
     title is `Proposal <Quote Number> <YYYY-MM-DD> <HH:MM> UTC`, so each send
     is distinct.
   - The progress screen embeds `c:rlmDocStatusMonitor`, the Create Proposal
     recheck pattern, which moves on when the DocumentGenerationProcess status
     changes. **Check status** forces a recheck. While the status is still
     InProgress or Waiting, a **Recheck** screen loops back.
   - On Success, `RLM_ReturnPDFDocument` resolves the PDF ContentVersion.
4. **Send.** The flow uses the standard Send Email action (`emailSimple`):
   - **Recipient:** the Quote Contact. **Related record:** the Quote.
   - **Template:** `Servomex_Proposal`. **Attachment:** the PDF.
   - **Sender:** the running user (`senderType = CurrentUser`; there's no
     Org-Wide Email Address).
   - The email is logged on send, so it appears on the Quote's Activity timeline.
5. **Record.** Status is set to **Presented**, and the rep sees
   "Sent to <name> (<address>)". The Proposal (PDF and the intermediate DOCX)
   stays under the Quote's Files.

**Failure handling.** If generation fails (Failure or Blocked, showing the
docgen response text), no PDF is found, the send fails, or the Status update
fails, the flow shows the error on a screen and leaves Status unchanged. A
Proposal that was already generated stays on the Quote.

**Re-sending** is allowed from every Status except Accepted and Denied,
including Presented. Each send produces a new Proposal. There are no "last
sent" fields; the Files and the logged emails are the history.

## The Demo Inbox Address safety net

Send Proposal sends only to a Quote Contact whose email is a Demo Inbox Address
(`martin.biondi+<alias>@piercewashington.com`). It checks the address with
`DemoInboxAddress`, the invocable **Check Demo Inbox Address**, the same module
the contact email rewrite uses. Every Proposal therefore lands in the
presenter's mailbox, never a real customer's.

## Email template

| Part | Content |
|------|---------|
| Subject | `Servomex proposal {!Quote.QuoteNumber}` |
| Body | Greets `{!Contact.FirstName}`, names `{!Quote.Name}`, states the grand total as `{!Quote.TotalPrice}` and `{!Quote.ExpirationDate}`, and is signed with the sender's name |

`{!Quote.GrandTotal}` merges as blank in a Classic template, so the body uses
`TotalPrice`. That equals the grand total unless the Quote carries tax or
shipping, which the demo quotes don't.

It's a Classic HTML template (`custom`) with a plain-text version. Edit the
wording in `force-app/main/default/email/Servomex/` and redeploy; the flow
doesn't change.

## Quote record page placement

rlm-base-dev's UX assembly (`assemble_and_deploy_ux`) regenerates
`RLM_Quote_Record_Page`, including its explicit highlights-panel action list,
and redeploys its org-default and `RLM_Revenue_Cloud` app-default assignments.
To stay out of that path:

- `Servomex_Quote_Record_Page` is a fork of the assembled page with
  `Quote.Servomex_Send_Proposal` added after Create Proposal. The fork drops the
  `IsLargeDeal` field, because the Metadata API rejects it on deploy ("couldn't
  retrieve or load the information on the field").
- `assign_servomex_quote_page` assigns the fork in the `RLM_Revenue_Cloud` app
  **per profile** (default `Admin`), which UX assembly doesn't write. A profile
  assignment beats the app and org defaults.

To show the action to more profiles, re-run the assignment with
`-o profiles Admin,<Profile>`.

**Drift:** the fork doesn't pick up later rlm-base-dev changes to the Quote page.
To refresh it, retrieve `RLM_Quote_Record_Page` from the org, re-apply the
one-line action insert and the label, and redeploy.

## Dependencies

- rlm-base-dev **docgen** deployed to the org: the `RLM_DocumentGenerationCreate`
  and `RLM_ReturnPDFDocument` classes, the `rlmDocStatusMonitor` LWC, and active
  Quote templates. See [docgen setup](../guides/docgen-setup.md).
- The Demo Inbox Address module and contact email rewrite (`deploy_servomex`,
  `rewrite_contact_emails_to_demo_inbox`). Run the rewrite before the first send.
- Email deliverability set to **All email**.

**Troubleshooting.** If every template fails with "Could not Enqueue to Kafka … contentVersion {0}"
or "invalid object IDs in the Doc Generation Additional Input", the org's docgen
templates or class are broken, not Send Proposal. See #74 for the 2026-11-20
`servomex` repair: new template versions (v2) and rlm-base-dev's current
`RLM_DocumentGenerationCreate`.

## Backup demo quote

`create_backup_demo_quote` gives the presenter a send-ready Quote to fall back
on if the live build runs long:

```bash
cci task run create_backup_demo_quote --org servomex                 # create or reset
cci task run create_backup_demo_quote --org servomex -o dry_run true # read-only plan
python3 scripts/demo/backup_demo_quote.py --org servomex [--dry-run] # without CCI (sf alias)
```

The task wraps `scripts/demo/backup_demo_quote.py` and passes it the org
username. The script uses the sf CLI and never an access token. Each run does
the following:

1. **Checks the Quote Contact.** Lars Eriksson on NordicGas AS must hold a Demo
   Inbox Address, checked with the same `DemoInboxAddress` action. If he
   doesn't, the run stops and tells you to run
   `rewrite_contact_emails_to_demo_inbox` first.
2. **Ensures the Opportunity.** *NordicGas AS — Analyser Upgrade (Backup Demo)*
   is created when missing, in the Account's currency (USD).
3. **Ensures the Quote.** *NordicGas AS — Backup Demo Quote* is created through
   Place Sales Transaction, so the pricing engine prices it. Lars is the Quote
   Contact, and it expires 30 days out. The lines are 1 × SERVOPRO 4900
   Multigas Analyser (`SMX-4900-MG`) and 2 × Calibration Gas Kit
   (`SMX-SPA-CALG`), USD 48,070. The SERVOFLEX Mini MP is deliberately left
   out, because its model changes often.
4. **On later runs,** it reuses the same Quote and resets it to **Draft**. It
   also restores Lars as Quote Contact if he was changed, and extends a lapsed
   expiration date. Nothing is deleted, so earlier Proposal Files and logged
   emails stay on the Quote.

The Opportunity and Quote are found by name, so don't rename them. If the run
finds two records with the backup name, or a backup Quote with no priced lines,
it stops. Delete the extra or broken record by hand and re-run.

## Manual check

There's no automated test, because document generation is asynchronous and
doesn't run in Apex tests. Check in the org:

- **Happy path:** on a Quote with Lars Eriksson as Quote Contact, the email with
  the PDF reaches `martin.biondi+lars.eriksson@piercewashington.com`, Status
  becomes Presented, and the email and File are on the Quote.
- **Re-send** from Presented adds a second Proposal.
- **Refusals:** no Quote Contact, a non-Demo Inbox Address, Accepted, and Denied.
