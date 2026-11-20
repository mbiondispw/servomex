# MiniMP5200 Constraint Model

Configuration rules for the SERVOFLEX Mini MP Portable Analyser (SKU `05230A1`),
hand-authored from the workbook *5230A1 Product configuration and pricing* (spec #32,
ticket #36). It uses the `rlm-base-dev` constraint dataset layout:

| File | Purpose |
|---|---|
| `blobs/ESDV_MiniMP5200_V1.ffxblob` | **The model.** Plain-text CML that `import_cml` uploads verbatim. |
| [`scripts/cml/MiniMP5200.cml`](../../../../scripts/cml/MiniMP5200.cml) | Reference copy. Keep it byte-identical to the blob (`cp` the blob over it). |
| `ExpressionSet.csv`, `ExpressionSetDefinitionVersion.csv`, `ExpressionSetDefinitionContextDefinition.csv` | The Expression Set (`UsageType = Constraint`), version `MiniMP5200_V1` and its `RLM_SalesTransactionContext` binding. |
| `ExpressionSetConstraintObj.csv` | One `Type` association binding type `MiniMP5200` to the Mini MP product. There are no `Port` rows because the Mini MP is a single product, not a bundle. |
| `Product2.csv` | Placeholder Id → product Name, which `import_cml` uses to resolve the `Type` association in the target org. |

The Ids in these CSVs are mnemonic placeholders (`…MINIMP`). `import_cml` remaps them
against the target org.

## Binding to the attributes

The CML attribute names are the `AttributeDefinition.DeveloperName` values
(`SMX_05230A1_<ATTRIBUTE>`), and the domain values are the `AttributePicklistValue.Value`
labels. Both are generated from the approved
[05230A1 Manifest](../../../sap/servomex-05230a1/manifest.yaml). Changing a label or code in
the Manifest means changing this model too.

Attributes with no rule are not declared and keep their PCM defaults: Supply Power, Inlet
Coupler, Exhaust / Vent Outlet (Rear Panel by default, Front Panel always allowed), User
Manual, Printer and the 12/24V Vehicle Power Adaptor.

## Rules

| Attribute | Rule | Workbook |
|---|---|---|
| Measurement 1 | Standard Accuracy only for A. Industrial for A/B/D. High Accuracy for A/C/E. CO2 ranges only for A. Each Standard Variant leaves one value, which becomes its default. | E17:E23 |
| Measurement 2 | Anything other than None only for A. A CO2 range is unavailable when it matches Measurement 1 (100%↔3, 50%↔4, 25%↔5, 10%↔6). That conflict carries the only explicit message. | E25:E28 |
| Sampling System | AFCD for A/B/C, Internal Pump for A/D/E. AFCD is the initial value for A. | E30:E31 |
| mA Output | Derived: Single when Measurement 2 is None, Dual otherwise. Not configurable. | E33:E34 |
| Side Panel Accessories | Sample Conditioning Panel only when Measurement 1 ≠ 1 and the Sampling System is Internal Pump. Flow Meter + Valve only with Internal Pump. Flow Meter only with AFCD. | E52:E54 |
| Probe Holder | Derived: Supplied with the Sample Conditioning Panel, Supplied : Including Filter with either flow meter panel. Empty and hidden without a side panel. Not configurable. | E56:E57 |
| Sample Probe | Fixed at Not Supplied without a side panel. | B59 |
| Transport Case | Fixed at Not Supplied without a side panel. Otherwise it defaults to Supplied and stays editable. | B64, E66 |

The Mini MP Configuration keeps a fixed Domain, so a rep can always switch Standard
Variant. Every other ruled attribute uses **Domain Pruning**
(`domainComputation = true`), so ruled-out values are not offered. The derived and
defaulted attributes (Sampling System, mA Output, Probe Holder, Sample Probe, Transport
Case) are `peelable`, so the engine re-derives them when another choice changes. Measurement
1 and 2 are not peelable, so a rep's measurement choice is never silently replaced.

## Known limitations

- **Comma-bearing values cannot be constrained.** The engine splits a comma-separated
  attribute value, so a rule comparing against "Oxygen, Standard Accuracy",
  "Oxygen, Industrial" or "Oxygen, High Accuracy" never matches. Today the Standard Variants
  do not move Measurement 1 to their Oxygen cell, and Standard Accuracy is not pruned from
  them or from the Sample Conditioning Panel rule. The CO2 gating works. The fix is
  comma-free picklist values (tracked as a follow-up issue).
- **Place Sales Transaction keeps or silently resolves a conflicting request.** It does not
  refuse it. The configurator `configure` action reports the conflict and its message on the
  saved line. The quote check judges rejections that way, and otherwise checks that the
  requested combination was not kept.

## Deploy

Run from the `rlm-base-dev` checkout, which has the CML tasks. `<servomex>` is this
repository's path, and `servomex` is both the CCI and the sf alias. The attributes (#34)
must already be loaded.

```bash
cd ../rlm-base-dev
M=<servomex>/datasets/constraints/servomex/MiniMP5200

cci task run validate_cml -o data_dirs "$M"                 # 0 errors
cci task run import_cml --org servomex -o data_dir "$M" -o dry_run true
cci task run import_cml --org servomex -o data_dir "$M"

# A standalone import never redeploys an active version: cycle it.
# manage_expression_sets ignores --org and runs against the CCI default org.
cci org default servomex
cci task run manage_expression_sets -o operation deactivate_versions -o version_full_names MiniMP5200_V1
cci task run manage_expression_sets -o operation activate_versions -o version_full_names MiniMP5200_V1
```

Reimporting is repeatable: `import_cml` upserts the Expression Set by `ApiName` and, on a
clean pass, replaces the model's existing association rows.

## Verify

Reading `ConstraintModel` back only proves the upload was stored. The configurator proves
deployment. Run the Mini MP quote check, which places real quotes with configuration rules
executed:

```bash
.venv/bin/python tests/quote-check/quote_check.py --org servomex
```

The `minimp-rules-*` scenarios in
[`minimp-05230a1.yaml`](../../../../tests/quote-check/scenarios/minimp-05230a1.yaml) cover
SV01 defaults, the derived values, and the rejected combinations. A scenario with
`expect.rejected` passes when the configurator reports the conflict (optionally with a
given message), or when the org did not keep the requested combination.
