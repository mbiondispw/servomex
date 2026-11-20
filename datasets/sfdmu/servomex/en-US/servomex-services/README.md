# servomex-services Data Plan

Adds the two per-Service-Day service products that Servomex reps quote in a
Service Upsell (spec #54, ticket #55):

| SKU / Product Code | Product | Price |
|--------------------|---------|-------|
| `SMX-SVC-TRN-DAY` | Operator Training — per Service Day | £1,606.80 |
| `SMX-SVC-SAT` | Site Acceptance Test (SAT) — per Service Day | £1,606.80 |

Quantity on a quote line is the number of Service Days.

## Provenance

The price is Servomex's 2021 UK site daily rate from the margin-calculator
workbook `621044384_MarginCalc(r2v9).xlsx`, sheet `Lookup Tables`, cell `AC32`
(1606.8 GBP). The workbook is customer material and is not in the repo.

## What the plan sets

- **Product2:** unit of measure `Day` (`QuantityUnitOfMeasure`), not configurable
  (`ConfigureDuringSale = NotAllowed`), not sold only with other products, active.
  The descriptions carry the search terms "operator training day" and
  "SAT" / "site acceptance test".
- **ProductSellingModelOption:** the org's existing `One-Time` selling model, as
  the **default** option. The Quote Agent refuses products without a default.
- **PricebookEntry:** one active GBP entry per product in the `Standard Price
  Book`, linked to `One-Time`. No other currencies, no Cost Book entries.
- **ProductCategoryProduct:** primary category `Service & Spares` in catalog
  `Gas Analyzers`.

The existing 2-day package `SMX-SVC-TRN` is not in this plan and is never
touched. It has no SKU, so it cannot match these records.

## Prerequisites

- The org already has the `One-Time` ProductSellingModel, the `Standard Price
  Book`, and exactly one ProductCategory named `Service & Spares` (in catalog
  `Gas Analyzers`).
- SFDMU v5.6.4+ (`sf sfdmu run`).
- CumulusCI 4.10.1+, and the target org imported into the `rlm-base-dev` keychain
  once: `cci org import <sf-alias> <cci-alias>`.

## Load

This project defines no data tasks. The `load_sfdmu_data` task is run from a
checkout of the sibling `rlm-base-dev` CumulusCI project, pointed at this plan by
absolute path:

```bash
cd <rlm-base-dev>
cci task run load_sfdmu_data --org <cci-alias> \
    -o pathtoexportjson <this-repo>/datasets/sfdmu/servomex/en-US/servomex-services
```

The task writes the org's credentials into `export.json` while it runs. Never
commit it mid-load; afterwards restore it and delete SFDMU's working folders:

```bash
git checkout -- datasets/sfdmu/servomex/en-US/servomex-services/export.json
rm -rf datasets/sfdmu/servomex/en-US/servomex-services/{reports,source,target}
```

## Post-load: rebuild the catalog search index

Product search only finds the products once the Product Catalog search index is
rebuilt. From `rlm-base-dev`:

```bash
cci task run rebuild_search_index --org <cci-alias> -o build_type FULL -o raise_on_failure True
```

The build is asynchronous; allow several minutes. Try `-o build_type INCREMENTAL`
first when the index was rebuilt recently; the org rejects an incremental build
("Too much time has elapsed since you last reindexed") after a long gap. Check
the build with `GET /services/data/v66.0/connect/pcm/index/snapshots`.

## Post-load: refresh the price book entry decision table

Pricing reads price book entries from the `Price_Book_Entry_Decision_Table_v2`
decision table, not from `PricebookEntry` directly, and incremental sync is off.
Until it is refreshed, Place Sales Transaction rejects the new products with
`Could not find product with ID: …`, and product discovery shows no price. From
`rlm-base-dev`:

```bash
cci task run refresh_dt_default_pricing --org <cci-alias> \
    -o developerNames Price_Book_Entry_Decision_Table_v2
```

The refresh is asynchronous and usually completes in under a minute. Check
`SELECT RefreshStatus, LastSyncDate FROM DecisionTable WHERE DeveloperName =
'Price_Book_Entry_Decision_Table_v2'`.

## Verify

```bash
python tests/quote-check/quote_check.py --org <sf-alias> \
    --scenarios tests/quote-check/scenarios/service-days.yaml
```

## Objects

SFDMU loads the objects in this order, parent before child.

| # | Object | Operation | External ID | Records |
|---|--------|-----------|-------------|---------|
| 1 | Product2 | Upsert | `StockKeepingUnit` | 2 |
| 2 | ProductSellingModelOption | Upsert | `Product2.StockKeepingUnit;ProductSellingModel.Name` | 2 |
| 3 | PricebookEntry | Upsert | `Product2.StockKeepingUnit;Pricebook2.Name;ProductSellingModel.Name;CurrencyIsoCode` | 2 |
| 4 | ProductCategoryProduct | Upsert | `ProductCategory.Name;Product.StockKeepingUnit` | 2 |

SFDMU adds the referenced `ProductSellingModel`, `Pricebook2` and
`ProductCategory` records read-only, matched by `Name`.

## Identity Strategy

`Product2` matches on the direct field `StockKeepingUnit`. Every query filters
to the two SKUs, so the plan can only match its own records.

`ProductSellingModelOption`, `PricebookEntry` and `ProductCategoryProduct` have
no direct identity field. Their keys are single-hop traversals that include the
product SKU, which SFDMU 5.6.4+ matches under `Upsert` (the same pattern as
`PricebookEntry` in `servomex-minimp-05230a1`). None uses a 2-hop traversal.
A second load against `servomex` processed 0 records on every object and left
exactly two products, two selling model options, two price entries and two
category assignments.

## Safety

- Every object uses `Upsert`. No object uses `deleteOldData`. Nothing in this
  plan deletes org records.
