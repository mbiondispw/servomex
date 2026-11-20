# Servomex Quote Agent

`SMX_Revenue_Quote_Management` (label *Servomex Quote Agent*) is a repo-owned
Agentforce Employee Agent. It is a trimmed copy of rlm-base-dev's
`RLM_Revenue_Quote_Management`, keeping only the **Product Selection** and
**Quote Management** subagents (see
[ADR 0001](../../docs/adr/0001-servomex-quote-agent.md)). It runs alongside the
org's template `Revenue_Quote_Management` agent, which stays active and unchanged.

Changes from the upstream copy:

- Dropped Product Configuration, Quote Lifecycle Management and Consumption
  Management; the router sends those requests to *off_topic*.
- `Get_Quote_Record_Card` (`flow://RLM_AI_Get_Quote_Record_Card`) is replaced by
  the standard **Get Record Details** action, and `Get_QuoteLineItem_from_Quote`
  (`flow://RLM_AI_Get_QuoteLineItem_from_Quote`) by the standard **Query Quote
  Lines** action. Nothing `RLM_AI_*` is referenced or deployed.
- Quote Management resolves Training and SAT requests to the per-Service-Day
  products (`SMX-SVC-TRN-DAY`, `SMX-SVC-SAT`).
- Quote Management has a **Create Service Opportunity** action
  (`flow://SMX_Create_Opportunity`, #57). When the rep names an account but no
  opportunity, the agent proposes a new opportunity, asks for one confirmation,
  then creates the opportunity, its quote and the lines. The flow sets Stage
  Proposal/Quote, the Standard Price Book and Next Step "Send services quote".
  Name defaults to "‹Account Name› — Services — ‹YYYY-MM-DD›", close date to
  today + 30, and currency to the account's; each input overrides its default.
  A named or on-screen opportunity is quoted as is, and a Closed Won or Closed
  Lost opportunity is never quoted.

| Path | What it is |
|------|------------|
| `aiAuthoringBundles/SMX_Revenue_Quote_Management/` | The agent definition (Agent Script) |
| `flows/SMX_Create_Opportunity.flow-meta.xml` | Autolaunched flow behind Create Service Opportunity |
| `permissionsets/SMX_QuotingAgent.permissionset-meta.xml` | Agent Access, run access to `SMX_Create_Opportunity`, plus the object access the quote actions need |
| `tests/smx-quote-agent/` | Agentforce Testing Center spec |

## Deploy, publish and activate

The tasks live in rlm-base-dev (CCI ≥ 4.10.1). Run them from the rlm-base-dev
checkout and pass **absolute** paths into this repo. Take the shared org lock
first when the org is shared.

```bash
SMX=/path/to/servomex/unpackaged/post_agents
RLM=/path/to/rlm-base-dev

# The agent's Create Service Opportunity action targets this flow, so deploy it first:
sf project deploy start -o <sf-alias> --source-dir $SMX/flows   # from an sfdx project dir
(cd $RLM && cci task run deploy_agents   --org servomex -o path         $SMX/aiAuthoringBundles)
(cd $RLM && cci task run publish_agents  --org servomex -o bundles_path $SMX/aiAuthoringBundles)
(cd $RLM && cci task run activate_agents --org servomex -o bundles_path $SMX/aiAuthoringBundles)
# The permission set's agentAccesses needs the published Bot, so deploy it last:
(cd $RLM && cci task run deploy_agent_permission_sets --org servomex -o path $SMX/permissionsets)
```

To change an active agent, re-run `publish_agents` (it creates a new version),
then `activate_agents`. To check the bundle compiles without writing to the org,
copy it into a scratch sfdx project and run
`sf agent validate authoring-bundle -o <sf-alias> -n SMX_Revenue_Quote_Management`.

Assign `SMX_QuotingAgent` to every user who holds `RLM_QuotingAgent`:

```bash
sf data query -o <sf-alias> -q "SELECT Assignee.Username FROM PermissionSetAssignment WHERE PermissionSet.Name = 'RLM_QuotingAgent'"
sf org assign permset -o <sf-alias> -n SMX_QuotingAgent -b <username> [-b <username> ...]
```

## Test

The agent test needs the Service Upsell products from the `servomex-services`
plan (#55) **and a rebuilt product catalog index**: until the index includes
them, the standard add-line flow answers "Could not find product with ID".
It also needs the fixture account and opportunity. Agent tests cost Flex
Credits; run only the specs you need. Run these from this repo's root.

```bash
# 1. Fixture: GBP account "Service Upsell Test Customer", its open
#    "Service Upsell Existing Opportunity" and its Closed Lost
#    "Service Upsell Closed Opportunity" (re-runnable).
sf apex run -o <sf-alias> -f scripts/apex/smxServiceUpsellFixture.apex

# 2. Agent test (from rlm-base-dev).
(cd $RLM && cci task run test_agents --org servomex -o tests_path $SMX/tests/smx-quote-agent)

# 3. Records check: 2 x SMX-SVC-TRN-DAY and 1 x SMX-SVC-SAT at 1606.80 from the
#    GBP price book entry, quote TotalPrice 4820.40, on the existing and the
#    new opportunity. The opportunity check shows the new opportunity's
#    defaults and that the closed opportunity has no quote.
sf data query -o <sf-alias> -f scripts/soql/smxServiceUpsellQuote.soql
sf data query -o <sf-alias> -f scripts/soql/smxServiceUpsellOpportunity.soql

# 4. Cleanup: deletes the test account's quotes and agent-created
#    opportunities, keeps both fixture opportunities.
sf apex run -o <sf-alias> -f scripts/apex/smxServiceUpsellCleanup.apex
```
