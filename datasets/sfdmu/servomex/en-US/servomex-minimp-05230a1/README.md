# servomex-minimp-05230a1 Data Plan

Generated SFDMU plan converting workbook `5230A1 Product configuration and pricing.xlsx` into Revenue Cloud attributes for Product `05230A1`.

> **Generated artifact.** Do not edit by hand. Edit the approved manifest and
> re-run `scripts/ai/generate_sap_attribute_migration.py`.

## Prerequisites

- Product `05230A1` already exists in the target org. This plan never creates Products.
- The one-time product bootstrap has run, so the product carries SKU `05230A1`: `sf apex run --file scripts/apex/bootstrapMiniMpProduct.apex --target-org <sf-alias>`.
- SFDMU v5.6.4+ (`sf sfdmu run`).
- CumulusCI 4.10.1+, and the target org imported into the `rlm-base-dev` keychain
  once: `cci org import <sf-alias> <cci-alias>`.

## Load

This project defines no data tasks. The `load_sfdmu_data` task is
run from a checkout of the sibling `rlm-base-dev` CumulusCI project, pointed at
this plan by absolute path:

```bash
cd <rlm-base-dev>
cci task run load_sfdmu_data --org <cci-alias> \
    -o pathtoexportjson <this-repo>/datasets/sfdmu/servomex/en-US/servomex-minimp-05230a1
```

The task writes the org's credentials into `export.json` while it runs and leaves
the file reformatted afterwards. Never commit it mid-load; restore it after the
load with:

```bash
git checkout -- datasets/sfdmu/servomex/en-US/servomex-minimp-05230a1/export.json
```

## Objects

SFDMU loads the objects in this order, parent before child, so every lookup
resolves against a record the previous step already wrote.

| # | Object | Operation | External ID | Records |
|---|--------|-----------|-------------|---------|
| 1 | AttributePicklist | Upsert | `Code` | 15 |
| 2 | AttributePicklistValue | Upsert | `Code` | 49 |
| 3 | AttributeDefinition | Upsert | `Code` | 15 |
| 4 | AttributeCategory | Upsert | `Code` | 1 |
| 5 | AttributeCategoryAttribute | Upsert | `AttributeCategory.Code;AttributeDefinition.Code` | 15 |
| 6 | ProductClassification | Upsert | `Code` | 1 |
| 7 | ProductClassificationAttr | Upsert | `Name` | 15 |
| 8 | Product2 | Update | `StockKeepingUnit` | 1 |
| 9 | ProductAttributeDefinition | Upsert | `Name` | 15 |
| 10 | PricebookEntry | Upsert | `Product2.StockKeepingUnit;Pricebook2.Name;ProductSellingModel.Name;CurrencyIsoCode` | 1 |
| 11 | AttributeBasedAdjRule | Upsert | `Name` | 837 |
| 12 | AttributeAdjustmentCondition | Upsert | `AttributeBasedAdjRule.Name;AttributeDefinition.Code;Product.StockKeepingUnit` | 4185 |
| 13 | AttributeBasedAdjustment | Upsert | `AttributeBasedAdjRule.Name;PriceAdjustmentSchedule.Name;Product.StockKeepingUnit;ProductSellingModel.Name;CurrencyIsoCode` | 837 |

## Identity Strategy

Generated codes are source-qualified as `SMX-05230A1-<attribute>[-<value>]` so that repeated
raw workbook codes such as `A`, `X`, `1`, and `2` cannot collide globally. The raw workbook
option code is preserved in `AttributePicklistValue.Abbreviation`, and the raw workbook
attribute id in `AttributeDefinition.SourceSystemIdentifier`.

`ProductClassificationAttr` and `ProductAttributeDefinition` use generated `Name`
values as direct external ids, because SFDMU v5 cannot reliably upsert on external
ids composed only of relationship traversals. `AttributeCategoryAttribute` has no
direct identity field, so it is the one object matched by traversal.

Each Option Adder combination's `AttributeBasedAdjRule` is named
`<prefix>-ADDERS-<value code>-…`, one code per price-impacting attribute in manifest order.
Its condition and adjustment have no direct identity field, so they match on
rule name, attribute, product, and (for the adjustment) schedule, selling model,
and currency, which SFDMU 5.6.4+ matches under `Upsert`.

`PricebookEntry` has no direct identity field either. It matches on SKU, price
book, selling model, and currency, which SFDMU 5.6.4+ matches under `Upsert`.

## Safety

- No object uses `deleteOldData`. Nothing in this plan deletes org records.
- `Product2` uses `Update`, scoped to `StockKeepingUnit = '05230A1'`, and writes only
  `BasedOn.Code`. No other Product field is touched, and no Product is created.
- `PricebookEntry` uses `Upsert`, scoped to `Product2.StockKeepingUnit = '05230A1'`. It sets the
  GBP `One-Time` entry in `Standard Price Book` to 4500, updating the existing entry in place.
- The Option Adder objects use `Upsert`; conditions and adjustments are scoped to
  `Product.StockKeepingUnit = '05230A1'`. Each adjustment is a flat GBP amount on
  `Standard Attribute Based Adjustment`, written as a negative `AdjustmentValue` because a
  positive `Amount` adjustment is a discount. The pricing procedure reads them through the
  `Attribute_Based_Adjustment_Decision_Table`; refresh it after every load.

## Validate

```bash
python scripts/validate_sfdmu_v5_datasets.py --dataset datasets/sfdmu/servomex/en-US/servomex-minimp-05230a1
```

## Warnings

The plan does not yet implement every rule the source states. No Revenue Cloud constraints were generated, so loading this plan does **not** make every generated option combination valid.

- MA_OUTPUT-option-adders: MA_OUTPUT has workbook prices but is not price-impacting, so its Option Adders are not applied (it adds 0).
- PROBE_HOLDER-option-adders: PROBE_HOLDER has workbook prices but is not price-impacting, so its Option Adders are not applied (it adds 0).
- SAMPLE_PROBE-option-adders: SAMPLE_PROBE has workbook prices but is not price-impacting, so its Option Adders are not applied (it adds 0).
- SIDE_PANEL_ACCESSORIES-option-adders: SIDE_PANEL_ACCESSORIES has workbook prices but is not price-impacting, so its Option Adders are not applied (it adds 0).
- TRANSPORT_CASE-option-adders: TRANSPORT_CASE has workbook prices but is not price-impacting, so its Option Adders are not applied (it adds 0).
- 05230A1-variant-discount: The workbook gives the Standard Variants "10% discount off total" (F5:F8). No variant discount is generated yet, so a Standard Variant prices at its full base plus Option Adders.
- 05230A1-option-dependencies: The workbook's Attribute dependency (column B) and Option Dependency (column E) rules are not generated. They belong to the hand-authored MiniMP5200 Constraint Model, so no generated option combination is proven valid yet.

See `conversion-report.md` for source node dispositions and unresolved source logic.
