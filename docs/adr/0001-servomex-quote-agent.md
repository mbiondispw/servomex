# Servomex keeps its own Quote Agent, which creates the opportunity itself

The Revenue Quote Management template agent can only quote an existing
opportunity. Servomex reps should be able to ask for a Service Upsell quote
without creating an opportunity first. So this repository owns
`SMX_Revenue_Quote_Management`, a trimmed copy of rlm-base-dev's
`RLM_Revenue_Quote_Management` with only Product Selection and Quote Management.
It adds an action that creates a new opportunity for every quote, unless the
user names an existing opportunity or is on its record page. It is published
and activated with rlm-base-dev's agent tasks, and it runs alongside the org's
template agent rather than replacing it.

## Considered Options

- **Hand-edit the org's template agent in Agentforce Builder.** Rejected: a
  fresh org can't rebuild the agent, and the agent test has no stable agent
  definition to test.
- **Retrieve the org agent's metadata into the repo.** Rejected: the org
  generates suffixed topic and action names (`_16jWs000000k32v`), so the files
  don't carry between orgs.
- **Copy rlm-base-dev's whole agent.** Rejected: its Product Configuration and
  record-card actions need `RLM_AI_*` Apex and flows that this org doesn't have.
  Service products need no configuration.

## Consequences

- The org has two quote agents. The demo user is granted only
  `SMX_QuotingAgent`, so the presenter can't pick the wrong one.
- Changes to the upstream template, or to rlm-base-dev's copy, don't reach
  this agent automatically. Re-copy them on purpose.
