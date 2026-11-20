# Quote Check

Headless org verification: each scenario creates one real Quote in the target
org through Place Sales Transaction, lets the org configure (product defaults +
configuration rules) and price it, then checks the priced Quote Line Items.

```bash
python tests/quote-check/quote_check.py --org <sf-alias> [--only <scenario-name>]
```

- `--org` is an **sf CLI** alias or username (for example `servomex`), not a CCI alias.
- Needs PyYAML (`.venv/bin/python` works once `pip install PyYAML` is done there).
- Writes to the org: the scenario's test Account (created once, then reused) and
  one new Quote per scenario run. It never updates or deletes other records.
  Take the shared org lock before running it against a shared org.
- Exit `0` all scenarios passed, `1` a scenario failed or the org refused a request.

## Adding a scenario

Append to `scenarios/minimp-05230a1.yaml` (or add a new file and pass
`--scenarios <file>`). No code change is needed for line fields or attributes:

```yaml
- name: sv01-defaults-take-10-percent      # unique, used by --only
  account: direct                          # key under accounts:
  lines:
    - sku: 05230A1
      attributes:                          # Attribute Definition Code -> value picked
        SMX-05230A1-CONFIGURATION: Standard Variant (SV01)
  expect:
    lines:
      - sku: 05230A1
        fields:                            # any QuoteLineItem field -> expected value
          TotalPrice: 1234.56
        attributes:                        # Attribute Definition Code -> value on the line
          SMX-05230A1-SUPPLY_POWER: UK Mains
```

New accounts (for example a `Partner` account) go under `accounts:` with
`name`, `type` (Account.Type) and `currency`. Expectations the harness cannot
yet express (price adjustment rows, rejected configurations) need a small
extension to `check()` in `quote_check.py`.
