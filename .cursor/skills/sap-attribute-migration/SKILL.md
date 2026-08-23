---
name: sap-attribute-migration
description: >-
  Convert SAP product classification documents into Revenue Cloud attributes.
  Use when a SAP classification export (VC / characteristics PDF), SAP Class,
  or SAP Characteristic list must become Product Classifications, Attribute
  Definitions, Attribute Picklists, and Product Attribute Bindings. Covers
  extraction, manifest curation, the human approval gate, generator invocation,
  and conversion report review.
---

# SAP Product Attribute Migration

Converts a SAP classification document into a standalone, non-destructive
SFDMU plan. Probabilistic PDF extraction is deliberately separated from
deterministic record generation by a reviewed YAML manifest.

```
SAP PDF  ──extract──▶  manifest.yaml  ──human approval──▶  generator CLI  ──▶  SFDMU plan
                       (authoritative)                                        + conversion report
```

## Quick Rules

1. **The manifest is the source of truth.** Everything under the plan path is a
   generated artifact. Never hand-edit generated CSVs, `export.json`, the plan
   `README.md`, or `conversion-report.md`.
2. **Every source node gets a disposition.** `generated`, `excluded`,
   `deferred`, `superseded`, or `source-control`. Nothing disappears silently.
3. **Generation is gated on human approval.** The generator exits 2 until
   `approval.approved: true` is present with a reviewer and a date.
4. **Codes are source-qualified.** `SAP-<class>-<characteristic>[-<value>]`.
   Raw SAP codes like `A`, `X`, `1`, `2` repeat across characteristics and can
   never be Revenue Cloud record codes.
5. **Source identity is preserved, not reused as identity.** SAP characteristic
   id → `AttributeDefinition.SourceSystemIdentifier`. SAP option code →
   `AttributePicklistValue.Abbreviation`.
6. **Single permitted value ⇒ required, read-only, defaulted.** Multi-value
   characteristics stay optional and editable with no invented default.
7. **Missing dependency logic is a warning, never a constraint.** Record it
   under `unresolved:` in the manifest.
8. **The Product is resolved, never created.** `Product2` is `Update`-only,
   scoped to the SKU, writing only `BasedOn.Code`.

## DO NOT

- **DO NOT** edit anything under the generated plan path — edit the manifest
  and re-run the generator.
- **DO NOT** use `deleteOldData` or any `Delete` operation in a generated plan.
- **DO NOT** change `Product2` to `Upsert`. If the target Product is absent the
  migration must fail rather than create a Product from insufficient PDF data.
- **DO NOT** generate Revenue Cloud constraints from SAP dependency icons,
  labels, or inferred meaning.
- **DO NOT** guess a Revenue Cloud data type. Mark the characteristic
  `deferred` instead.
- **DO NOT** invent defaults, mandatory flags, or pricing impact that the
  source does not state.
- **DO NOT** add product-specific CCI tasks, flows, or feature flags. The
  generic `load_sfdmu_data` task is the deployment interface.

## Workflow

### 1. Extract

Parse the SAP classification document into an ordered list of source nodes.
Each node is either a **SAP Characteristic** (identifier + short text) or one
of its **Permitted Values** (option code + short text). Capture the page number
and the exact source line for every node.

### 2. Curate into a manifest

Write `datasets/sap/<slug>/manifest.yaml`. Assign a disposition to every node.

| Disposition | Meaning | Generates records |
|-------------|---------|-------------------|
| `generated` | Retained as a selling choice | Yes |
| `excluded` | Deliberately dropped, with a reason | No |
| `deferred` | Data type or modeling unresolved | No |
| `superseded` | Replaced by a retained variant (`superseded_by`) | No |
| `source-control` | SAP technical structure kept only for traceability | No |

Curation rules drawn from the source structure:

- Section-header characteristics (dummy value `1 / .`) become **Attribute
  Categories**, listed under `categories:`. Their dummy value generates nothing.
- Prefer product-specific `B` characteristics over overlapping generic
  variants. Mark each generic variant `superseded` by the retained one.
- Dependency-table references, variant-condition controls, BOM nodes,
  task-list nodes, configuration-profile nodes, and release controls are
  `source-control` or `excluded`.
- Options labeled `Not Used`, `NU`, or equivalent are excluded values with a
  reason.
- Correct only unambiguous customer-facing spelling errors. The exact source
  wording stays in `source.text`.

### 3. Get human approval

Stop. Present the dispositions to a human reviewer. Only the reviewer adds:

```yaml
approval:
  approved: true
  approved_by: <name>
  approved_on: <date>
```

Do not add this block on the human's behalf.

### 4. Generate

```bash
python scripts/ai/generate_sap_attribute_migration.py \
    --manifest datasets/sap/<slug>/manifest.yaml
```

Exit codes: `0` generated (warnings possible), `1` usage/IO error, `2` manifest
rejected. Rejections name the offending manifest path — fix the manifest, never
the output.

### 5. Review and validate

```bash
python scripts/validate_sfdmu_v5_datasets.py --dataset <plan.path>
tests/test-sap-attribute-migration.sh
```

Read `conversion-report.md` and confirm the disposition table matches what the
reviewer approved, and that every unresolved warning is still accurate.

### 6. Load

```bash
cci task run load_sfdmu_data -o pathtoexportjson <plan.path> --org <alias>
```

## Manifest Shape

```yaml
revision: 1
approval:
  approved: true
  approved_by: <name>
  approved_on: <date>
source:
  system: SAP
  document: <file name>
  sap_product: <SAP product id>
  sap_class: <SAP class id>
target:
  product_sku: <existing Product2.StockKeepingUnit>
  product_classification_name: <display name>
plan:
  path: datasets/sfdmu/<brand>/<locale>/<plan>
categories:
  - id: <SAP section-header characteristic id>
    label: <display name>
    disposition: generated
    source: { page: <n>, text: "<exact source line>" }
characteristics:
  - id: <SAP characteristic id>
    label: <display name>
    disposition: generated       # or excluded | deferred | superseded | source-control
    disposition_reason: <why>
    type: Picklist               # Picklist | Text | Number | Checkbox | Date | DateTime
    category: <category id>
    sequence: <n>
    source: { page: <n>, text: "<exact source line>" }
    values:
      - code: <raw SAP option code>
        label: <display value>
        disposition: generated   # or excluded (+ disposition_reason)
        source: { page: <n>, text: "<exact source line>" }
unresolved:
  - id: <topic>
    reason: <what the source references but does not contain>
```

## Generated Object Chain

Attribute Picklists and Definitions alone do not make attributes available on a
product. The chain must be complete:

```
AttributePicklist ──▶ AttributePicklistValue
        └──▶ AttributeDefinition ──▶ AttributeCategoryAttribute ──▶ AttributeCategory
                       └──▶ ProductClassificationAttr ──▶ ProductClassification
                                        └──▶ ProductAttributeDefinition ──▶ Product2
```

| Object | Operation | External ID |
|--------|-----------|-------------|
| AttributePicklist | Upsert | `Code` |
| AttributePicklistValue | Upsert | `Code` |
| AttributeDefinition | Upsert | `Code` |
| AttributeCategory | Upsert | `Code` |
| AttributeCategoryAttribute | Upsert | `AttributeCategory.Code;AttributeDefinition.Code` |
| ProductClassification | Upsert | `Code` |
| ProductClassificationAttr | Upsert | `Name` |
| Product2 | **Update** | `StockKeepingUnit` |
| ProductAttributeDefinition | Upsert | `Name` |

`ProductClassificationAttr` and `ProductAttributeDefinition` use generated,
source-qualified `Name` values as direct external ids because SFDMU v5 cannot
reliably upsert on external ids composed only of relationship traversals
(see SFDMU Bug 5 in `AGENTS.md`). `AttributeCategoryAttribute` has no direct
identity field, so it is the single object matched by traversal.

## Related

- `.cursor/skills/sfdmu-data-plans/SKILL.md` — SFDMU v5 rules and known bugs
- `.cursor/skills/revenue-cloud-data-model/SKILL.md` — RLM object relationships
- `CONTEXT.md` — canonical SAP-to-Revenue-Cloud vocabulary
