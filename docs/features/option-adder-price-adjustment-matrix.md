# Option Adders via a Price Adjustment Matrix

Status: **designed and generated, not wired** (#46, parent spec #32). The data plan,
decision table and object metadata are in the repo. Nothing in pricing reads them
yet. Wiring them in, and retiring the #35 combination rows, is a later ticket.

## Why the standard attribute adjustments don't stack

An **Option Adder** is the flat price a workbook option adds to the Mini MP line,
for example a rechargeable battery adds £1,292.

The standard *Attribute Discount* element reads
`Attribute_Based_Adjustment_Decision_Table`. That table matches on
`AttributeAdjConditionsHash` with `Equals`, a single hash over the values of
**every** price-impacting attribute on the line. Three consequences follow:

- each `AttributeBasedAdjustment` must condition on all price-impacting attributes;
- a line matches at most one row, so one row has to carry the whole combination's total;
- the row count is the product of the attributes' value counts.

#35 ships that for the demo. Its rows cover five defaulted attributes (Supply
Power, Measurement 1, Measurement 2, Inlet Coupler, Printer), 837 rules in all. The
other five priced attributes add £0: mA Output, Side Panel Accessories, Probe
Holder, Sample Probe and Transport Case. Adding them would multiply the row count,
and three of them have no static default, so the hash would often match nothing.

The Price Adjustment Matrix design below adds **one row per priced value** and lets
the pricing engine add up the rows that match. The Mini MP needs 25 rows, covering
all 10 priced attributes.

## What is in the repo

| Artifact | Path | Generated? |
|---|---|---|
| Matrix rows (SFDMU plan) | `datasets/sfdmu/servomex/en-US/servomex-minimp-05230a1-option-adder-matrix/` | Yes, from the manifest |
| Generator | `scripts/ai/generate_option_adder_matrix.py` | — |
| Generator CLI test | `tests/test-option-adder-matrix.sh` | — |
| Object `Option_Adder__c` | `unpackaged/post_option_adder_matrix/objects/` | No, product-agnostic |
| Decision table `Option_Adder_Matrix` | `unpackaged/post_option_adder_matrix/decisionTables/` | No, product-agnostic |
| Permission set `Option_Adder_Matrix` | `unpackaged/post_option_adder_matrix/permissionsets/` | No |

The rows come from the approved Manifest
`datasets/sap/servomex-05230a1/manifest.yaml`. Every retained picklist value with a
`price` becomes one row, and the price's workbook cell is kept in
`Source_Reference__c`. The generator validates the manifest exactly as the attribute
generator does: approval gate, provenance, and prices only on retained values. To
change a price, edit the manifest and run:

```bash
python scripts/ai/generate_option_adder_matrix.py --manifest datasets/sap/servomex-05230a1/manifest.yaml
```

**Retiring an adder.** The plan only upserts; nothing deletes. A row that was
simply left out would stay active in the org and keep adding its old price. So the
committed plan acts as the ledger: when a value loses its price, regeneration keeps
its row with `Is_Active__c = false`, and the next load deactivates it. Pricing the
value again makes the row active. Always regenerate over the committed plan
directory, and don't edit rows in the org, because the next load overwrites them.

The object, decision table and permission set are hand-authored. They hold no
product data, so one table serves every product that gets Option Adders.

### `Option_Adder__c`

| Field | Role |
|---|---|
| `Code__c` | Direct unique external id `<picklist value code>-<SKU>-<currency>`. The plan upserts on it, so reruns never duplicate. |
| `Product__c` → Product2 | Decision table input. |
| `Attribute_Picklist_Value__c` → AttributePicklistValue | Decision table input: the selected value. |
| `Attribute_Definition__c` → AttributeDefinition | The attribute. The picklist value implies it, so it is kept for reporting, not as an input. |
| `CurrencyIsoCode` | Decision table input. Rows are GBP, so a quote in another currency matches nothing. |
| `Adjustment_Type__c` | `Amount`. Mapped to the element's `AdjustmentType`. |
| `Adjustment_Value__c` | Minus the adder, e.g. `-1292`. Mapped to the element's `AdjustmentValue`. |
| `Is_Active__c` | The decision table reads active rows only. The generator sets it; see *Retiring an adder*. |
| `Source_Reference__c` | Workbook cell of the price, e.g. `Product Config and Pricing!F13`. |

The picklist value alone identifies the attribute, because a priced value always
belongs to its own characteristic's picklist. The attribute generator rejects
prices on shared picklists.

### `Option_Adder_Matrix` decision table

- `SingleSobject` on `Option_Adder__c`, usage `DefaultPricing`, `MediumVolume` / `HBASE`.
  This is the same shape as the org's `Attribute_Based_Adjustment_Decision_Table` and
  rlm-base-dev's PAM table `RLM_Channel_Program_Level_Partner`.
- Inputs, all `Equals` and combined `1 AND 2 AND 3`: `Product__c`,
  `Attribute_Picklist_Value__c`, `CurrencyIsoCode`.
- Outputs: `Adjustment_Type__c` and `Adjustment_Value__c`.
- Source criterion: `Is_Active__c = true`.
- Ships as **Draft**, so the deploy cannot change pricing. Wiring activates it.

## Pricing procedure design

This is the element design for the wiring ticket. Element and parameter names
follow the Winter '27 help, *Dynamic Pricing With Price Adjustment Matrix* and
*Example: Apply Discounts Sequentially*, and rlm-base-dev's shipped
`RLM_PRM_DISTI_Pricing_Procedure`.

### 1. Recipe mapping

Map the table in the active pricing recipe, `NGPDefaultRecipe`, as component type
`PriceAdjustmentMatrix`:

- `AdjustmentValue` → `Adjustment_Value__c`
- `AdjustmentType` → `Adjustment_Type__c`

`NGPDefaultRecipe` has no `PriceAdjustmentMatrix` mapping today, as read from the
org on 2026-11-20, so this is additive. rlm-base-dev automates it with
`configure_pricing_recipe_table_mappings` and a JSON payload like
`datasets/tooling/PricingRecipeTableMappings/prm_ngp_default.json`.

### 2. Procedure Output Resolution

Create a resolution record `Option_Adder_Stack`:

- Pricing Element: *Price Adjustment Matrix*
- Formula: `STACK(Adjustment_Value__c)`

`STACK` applies every matching row against the same input price, so the adders
add up. `SEQUENCE` would chain them; for flat amounts the result is the same.
`STACK` says what is meant: adders are independent.

### 3. The element

Add one **Price Adjustment Matrix** step, *Apply Option Adders*, to the Servomex
pricing procedure. That procedure is the source-controlled clone from #32; the
shipped procedures stay untouched.

| Section | Variable | Mapped to |
|---|---|---|
| Lookup table | — | `Option_Adder_Matrix` |
| Input rule variables | `Product__c` | line tag `Product` |
| | `Attribute_Picklist_Value__c` | tag `AttributePicklistValue` on the line's `SalesTransactionItemAttribute` node |
| | `CurrencyIsoCode` | tag `CurrencyIsoCode` |
| Input variables | Quantity | `LineItemQuantity` |
| | Input Unit Price | net unit price after List Price |
| Resolution variables | *Enable Output Resolution* | on |
| | Resolution Strategy | a Text constant `ResolutionStrategyOptionAdders` = `Option_Adder_Stack` |
| | Use As List | `Attribute_Picklist_Value__c` |
| Output variables | Net Unit Price | `NetUnitPrice` |
| | Include in Output | on (whether each adder gets its own waterfall entry is spike step 3) |

The `AdjustmentTypeField` and `AdjustmentValueField` parameters are Text
constants holding `Adjustment_Type__c` and `Adjustment_Value__c`. This follows the
`Constant_Adjustment*_RLM_Channel_Program_Level_Partner_PAM` pattern in the PRM
procedure.

The `SalesTransactionItemAttribute` node carries tags `AttributePicklistValue`,
`AttributeDefinitionCode`, `AttributeValue` and `PriceImpactingAttribute`, as read
from the org's `SalesTransactionContext__stdctx`. The help's multi-value pattern
uses a child node of the line with one unique key per row as the *Use As List*
input. The attribute node is exactly that: a child of the line with one row per
attribute.

**Placement.** Put the step after *List Price* and where *Attribute Discount* runs
today. It must come before the Standard Variant 10% step and the Channel Partner
Discount, because #32 discounts the full configured price, base plus every adder.

### How the 10 lookups stack

One element performs every lookup. The line's attribute node contributes one
picklist value per attribute that has one, so a Mini MP line passes up to 15 values
in the list. An unset attribute, such as Probe Holder without a side panel, passes
nothing. Each value is looked up with the line's product and currency:

- an unpriced value (UK Mains, Not Supplied, None…) matches no row and adds nothing;
- a priced value matches exactly one row;
- one value per attribute means at most one row per attribute, so a line matches at
  most 10 rows, one per priced attribute;
- `Option_Adder_Stack` applies all matched rows to the same input price.

Worked example: configuration A, Rechargeable Battery UK, Oxygen Industrial, CO2
10% FS second measurement, Internal Pump, Flow Meter + Valve, 1/8" NPT, Printer
Supplied, 1m SS sample probe. The Constraint Model derives Dual mA, Probe Holder
*Supplied : Including Filter* and Transport Case Supplied.

| Attribute | Value | Row matched | Adds (£) |
|---|---|---|---|
| Supply Power | Rechargeable Battery UK | `…SUPPLY_POWER-5` | 1,292 |
| Measurement 1 | Oxygen, Industrial | `…MEASUREMENT_1-1A` | 4,755 |
| Measurement 2 | CO2 10% FS | `…MEASUREMENT_2-4` | 4,750 |
| mA Output | Dual (derived) | `…MA_OUTPUT-2` | 1,170 |
| Inlet Coupler | 1/8" NPT | `…INLET_COUPLER-2` | 99 |
| Printer | Supplied | `…PRINTER-2` | 1,521 |
| Side Panel Accessories | Flow Meter + Valve | `…SIDE_PANEL_ACCESSORIES-2` | 1,054 |
| Probe Holder | Supplied : Including Filter (derived) | `…PROBE_HOLDER-2` | 467 |
| Sample Probe | 1m SS | `…SAMPLE_PROBE-3` | 133 |
| Transport Case | Supplied (derived) | `…TRANSPORT_CASE-2` | 806 |
| Sampling System, Configuration, Exhaust, Manual, Vehicle Adaptor | — | none | 0 |
| **Adders** | | 10 rows | **16,047** |

List price £4,500 plus £16,047 gives £20,547, before the Standard Variant and Channel
Partner steps. #35's combination rows price only Supply Power, both Measurements,
Inlet Coupler and Printer, so the same line gets £12,417 of adders there.

### Alternatives considered

- **Ten PAM elements, one per priced attribute**, each with a constant attribute
  code. Rejected. The line has no scalar tag per attribute: values live in the
  attribute node, so each element would still need a list input. A list of value
  *labels* also loses the pairing with the attribute: Printer, Probe Holder and
  Transport Case each have a value labelled *Supplied*, so a Printer element would
  fire on Transport Case Supplied. Keying on the picklist value avoids both
  problems with one element.
- **More `AttributeBasedAdjustment` combinations.** All 10 priced attributes give
  far more than #35's 837 rows, and need a default on every priced attribute.
  This is the limit #46 exists to remove.
- **Apex pricing hook** that sums adders before pricing. Kept as the fallback if the
  verification spike shows *Use As List* cannot read a child-node tag.

## Verify before wiring

The help documents each piece, but nothing has run end to end on this org. Run
these in a scratch org, or in `servomex` once the demo freeze is over, against a
**cloned, inactive** procedure version. Simulate before activating anything.

1. **Sign.** A row with `Adjustment_Value__c = -1292` must *raise* the net price by
   £1,292. If it lowers it, flip `ADJUSTMENT_SIGN` in the generator, regenerate and
   reload. The plan upserts, so no deletes are needed.
2. **List over the attribute node.** *Use As List* on the `AttributePicklistValue`
   tag returns one row per priced selection. If it can't read a child-node tag,
   fall back to the Apex hook above.
3. **Stacking.** The worked example above totals £16,047 in adders, and the price
   waterfall shows each adder. If the waterfall collapses them into one entry,
   record that and decide whether it is acceptable for the demo story.
4. **No false matches.** Unpriced selections add 0. A non-GBP quote adds nothing,
   because GBP is the only currency in scope (#32).
5. **Repricing.** Changing a priced attribute that isn't price-impacting (e.g.
   Transport Case today) still reprices the line. If it doesn't, the wiring ticket
   flags all 10 priced attributes price-impacting, after step 2 of the checklist
   below. Until then the extra flags would break #35's combination hash.

## Wiring checklist (later ticket)

1. Deploy `unpackaged/post_option_adder_matrix` and assign the `Option_Adder_Matrix`
   permission set to the loading user.
2. Load the matrix plan (see its README), then activate and refresh `Option_Adder_Matrix`.
3. Add the recipe mapping and the `Option_Adder_Stack` resolution record.
4. In the Servomex procedure: deactivate, add *Apply Option Adders*, reactivate.
5. Stop the #35 combination rows from also pricing the line, or every adder on the five
   combination attributes is charged twice. Either remove the *Attribute Discount* step
   from the Servomex procedure or end-date the Mini MP `AttributeBasedAdjustment`
   rows, then refresh `Attribute_Based_Adjustment_Decision_Table`. Only then change the
   price-impacting flags.
6. Re-run `tests/quote-check/quote_check.py` with scenarios that select priced options
   on all 10 attributes.

## Not done in #46

No org writes. The active pricing procedure and expression sets, the pricing
recipe, the existing decision tables, the `AttributeBasedAdjustment` rows, and the
Mini MP's price-impacting flags are all untouched.
