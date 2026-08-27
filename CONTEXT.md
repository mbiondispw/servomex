# CONTEXT

Canonical vocabulary for this repository. Use these terms in issues, proposals,
tests, and code. Implementation rules live in the skills that own each topic,
not here.

## SAP Product Attribute Migration

Terms for converting SAP product classification documents into Revenue Cloud
configurator attributes. Owning skill:
`.cursor/skills/sap-attribute-migration/SKILL.md`.

### Source-side terms (SAP)

| Term | Definition |
|------|------------|
| **SAP Product** | The SAP material identified in a classification document, e.g. `07930B1`. Resolved as an existing Revenue Cloud Product; never created by a migration. |
| **SAP Class** | The SAP classification grouping a set of characteristics, e.g. `CLASS_7930B`. Becomes a Product Classification. |
| **SAP Characteristic** | A single named property in a SAP Class, e.g. `C7900B_TPBASE`. Becomes an Attribute Definition when retained. |
| **Permitted-Value Set** | The set of option codes a SAP Characteristic allows. Becomes an Attribute Picklist. |
| **Permitted Value** | One option code and its short text within a Permitted-Value Set. Becomes an Attribute Picklist Value. |

### Target-side terms (Revenue Cloud)

| Term | Definition |
|------|------------|
| **Product Classification** | Reusable grouping that owns attribute assignments. The Revenue Cloud equivalent of a SAP Class. |
| **Attribute Definition** | Reusable definition of one configurable property, with a data type and an optional picklist. |
| **Attribute Picklist** | Reusable set of selectable values for picklist-typed Attribute Definitions. |
| **Attribute Picklist Value** | One selectable option within an Attribute Picklist. |
| **Classification Attribute Assignment** | `ProductClassificationAttr` — assigns an Attribute Definition to a Product Classification. |
| **Product Attribute Binding** | `ProductAttributeDefinition` — makes a Classification Attribute Assignment available on a specific Product. Without it, the attribute is not on the product. |

### Migration process terms

| Term | Definition |
|------|------------|
| **Manifest** | The reviewed, approved YAML file that is the authoritative migration input. Generated SFDMU data and the conversion report are derived artifacts. |
| **Shared Permitted-Value Set** | One Attribute Picklist declared once in the manifest and referenced by several SAP Characteristics that repeat the same options. |
| **Disposition** | The recorded decision for a source node: `generated`, `excluded`, `deferred`, `superseded`, or `source-control`. |
| **Source-qualified code** | A generated Revenue Cloud code namespaced by source system, class, characteristic, and value, so repeated raw SAP codes cannot collide globally. |
| **Conversion report** | The generated Markdown record of dispositions, generated counts, exclusions, and unresolved source logic. |
