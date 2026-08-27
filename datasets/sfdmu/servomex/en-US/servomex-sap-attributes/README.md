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

SFDMU loads the objects in this order, parent before child, so every lookup
resolves against a record the previous step already wrote.

| # | Object | Operation | External ID | Records |
|---|--------|-----------|-------------|---------|
| 1 | AttributePicklist | Upsert | `Code` | 40 |
| 2 | AttributePicklistValue | Upsert | `Code` | 170 |
| 3 | AttributeDefinition | Upsert | `Code` | 89 |
| 4 | AttributeCategory | Upsert | `Code` | 8 |
| 5 | AttributeCategoryAttribute | Upsert | `AttributeCategory.Code;AttributeDefinition.Code` | 89 |
| 6 | ProductClassification | Upsert | `Code` | 1 |
| 7 | ProductClassificationAttr | Upsert | `Name` | 89 |
| 8 | Product2 | Update | `StockKeepingUnit` | 1 |
| 9 | ProductAttributeDefinition | Upsert | `Name` | 89 |

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

## Warnings

The source document references logic it does not contain. No Revenue Cloud constraints were generated, so loading this plan does **not** make every generated option combination valid.

- CLASS_7930B-dependencies: The source document flags SAP dependency and variant-condition logic through the Dep. column and icons, but does not contain the rules themselves. No Revenue Cloud constraints were generated, and no generated option combination is proven valid.
- C7900B_TP01-measurement-1: The source supplies a Measurement 1, Range permitted-value set but no permitted values or data type for Measurement 1 itself, so the primary measured component is deferred and the retained range has no measured component to qualify.
- C7900-optical-path-lengths: The three optical path segments and their total are quoted as engineering measurements, but the source states no unit, no permitted values, and no data type. They are deferred, so the retained Total Path Length band is the only optical-length choice the configurator offers.
- C7900-process-application-inputs: Process temperature, process pressure, and dust loading are quoted as application inputs with no unit, permitted values, or scale. They are deferred and generate no Revenue Cloud rows.

See `conversion-report.md` for source node dispositions and unresolved source logic.
