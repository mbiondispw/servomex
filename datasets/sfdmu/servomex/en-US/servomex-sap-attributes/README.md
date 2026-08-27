# servomex-sap-attributes Data Plan

Generated SFDMU plan converting SAP Class `CLASS_7930B` (`07930B1 VC.pdf`) into Revenue Cloud attributes for Product `07930B1`.

> **Generated artifact.** Do not edit by hand. Edit the approved manifest and
> re-run `scripts/ai/generate_sap_attribute_migration.py`.

## Prerequisites

- Product `07930B1` already exists in the target org. This plan never creates Products.
- SFDMU v5.0.0+ (`sf sfdmu run`).

## Load

```bash
cci task run load_sfdmu_data -o pathtoexportjson datasets/sfdmu/servomex/en-US/servomex-sap-attributes --org <alias>
```

## Objects

| # | Object | Operation | External ID | Records |
|---|--------|-----------|-------------|---------|
| 1 | AttributePicklist | Upsert | `Code` | 23 |
| 2 | AttributePicklistValue | Upsert | `Code` | 113 |
| 3 | AttributeDefinition | Upsert | `Code` | 23 |
| 4 | AttributeCategory | Upsert | `Code` | 3 |
| 5 | AttributeCategoryAttribute | Upsert | `AttributeCategory.Code;AttributeDefinition.Code` | 23 |
| 6 | ProductClassification | Upsert | `Code` | 1 |
| 7 | ProductClassificationAttr | Upsert | `Name` | 23 |
| 8 | Product2 | Update | `StockKeepingUnit` | 1 |
| 9 | ProductAttributeDefinition | Upsert | `Name` | 23 |

## Identity Strategy

Generated codes are source-qualified as `SAP-CLASS_7930B-<characteristic>[-<value>]` so that repeated
raw SAP codes such as `A`, `X`, `1`, and `2` cannot collide globally. The raw SAP
option code is preserved in `AttributePicklistValue.Abbreviation`, and the raw SAP
characteristic id in `AttributeDefinition.SourceSystemIdentifier`.

`ProductClassificationAttr` and `ProductAttributeDefinition` use generated `Name`
values as direct external ids, because SFDMU v5 cannot reliably upsert on external
ids composed only of relationship traversals. `AttributeCategoryAttribute` has no
direct identity field, so it is the one object matched by traversal.

## Safety

- No object uses `deleteOldData`. Nothing in this plan deletes org records.
- `Product2` uses `Update`, scoped to `StockKeepingUnit = '07930B1'`, and writes only
  `BasedOn.Code`. No other Product field is touched, and no Product is created.

## Validate

```bash
python scripts/validate_sfdmu_v5_datasets.py --dataset datasets/sfdmu/servomex/en-US/servomex-sap-attributes
```

See `conversion-report.md` for source node dispositions and unresolved source logic.
