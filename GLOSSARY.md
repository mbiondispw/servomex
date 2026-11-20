# GLOSSARY

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
| **Disposition** | The recorded decision for a source node: `generated`, `excluded`, `deferred`, `superseded`, or `source-control`. A permitted value is `generated`, `excluded`, or `added` (generated beyond the source, with no provenance but a recorded reason). |
| **Source-qualified code** | A generated Revenue Cloud code namespaced by source system, class, characteristic, and value, so repeated raw SAP codes cannot collide globally. |
| **Workbook Source** | A non-SAP Manifest source: a spreadsheet cited by sheet and cell (`source.kind: workbook`). It has no SAP Class, so codes are namespaced by the SAP material. |
| **Conversion report** | The generated Markdown record of dispositions, generated counts, exclusions, added values, and unresolved source logic. |

## SAP Configuration Rules

Terms for the dependency logic that governs which SAP Characteristics and
Permitted Values a configuration may use, and its Revenue Cloud equivalent.

### Source-side terms (SAP)

| Term | Definition |
|------|------------|
| **Precondition** | A SAP rule, prefixed `PC_`, that suppresses its subject unless the rule holds. The subject is never offered while the condition is false. |
| **Selection Condition** | A SAP rule, prefixed `SC_`, that makes its subject relevant — and so answerable — when the rule holds. Independent of, and combinable with, a Precondition on the same subject. |
| **Rule Attachment** | The binding of a rule to its subject. A rule attaches either to a whole SAP Characteristic or to one Permitted Value within it; the two are different subjects with different effects. |
| **Rule Conjunction** | Several rules attached to one subject. All must hold for the subject to be offered; they are never alternatives. |
| **Release Gate** | A rule whose condition tests SAP release status rather than the configuration. It records whether a feature is sellable yet, not whether it fits the rest of the configuration. |

### Translation terms

| Term | Definition |
|------|------------|
| **Rule Reduction** | Rewriting a rule's condition against the Permitted Values actually retained, since a rule cannot name a value that no longer exists. A reduction may leave the condition unconditionally true or unconditionally false. |
| **Unreachable Value** | A Permitted Value that survives into an Attribute Picklist but that no configuration can select, because a reduced rule rules it out in every case. Retained rather than deleted, so the picklist stays faithful to its source. |

### Target-side terms (Revenue Cloud)

| Term | Definition |
|------|------------|
| **Constraint Model** | The declarative model, authored in Constraint Modeling Language (CML), that the Product Configurator solves to decide which values a configuration may hold. |
| **Domain** | The set of values an attribute may currently hold. Narrower than its Attribute Picklist whenever the Constraint Model rules values out. |
| **Domain Pruning** | Recomputing an attribute's Domain from the Constraint Model as the configuration changes, so ruled-out values stop being offered. Opt-in per attribute. |

## Quote Delivery

Terms for sending a quote's customer-facing document to the customer.

| Term | Definition |
|------|------------|
| **Quote Account** | The customer Account a Quote is for. Distinct from the seller's Account, which supplies the seller details on a document. |
| **Quote Contact** | The one Contact on the Quote Account who receives the quote. Every Quote that will be sent has one; it is never inferred from the Account's other Contacts. _Avoid_: account contact, primary contact. |
| **Proposal** | The customer-facing PDF generated from a Quote and sent to its Quote Contact. Each send produces a new Proposal. _Avoid_: quote document, quote PDF. |
| **Presented** | The Quote Status meaning a Proposal has been sent to the Quote Contact. Set only by a successful send. |
| **Demo Inbox Address** | An email address of the form `martin.biondi+<alias>@piercewashington.com`. The only kind of address a Contact in a demo org may hold, so no Proposal reaches a real customer. _Avoid_: plus-address, redirect address. |

## Service Upsell Quoting

Terms for quoting Servomex services to a customer who already owns an
analyser.

| Term | Definition |
|------|------------|
| **Service Upsell** | A services-only quote, on its own opportunity, for a Quote Account that already owns a Servomex analyser. Services sold with a new analyser are not an upsell. |
| **Service Day** | One Servomex engineer or trainer working on site for one day. The unit in which Training and SAT are sold. |
| **Training** | On-site instruction of the customer's operators in analyser operation, maintenance, and troubleshooting, sold in Service Days. |
| **Site Acceptance Test (SAT)** | On-site test, run with the customer after delivery, proving the installed analyser performs to specification. Sold in Service Days. _Avoid_: UAT. |
| **Factory Acceptance Test (FAT)** | Test at Servomex, before shipment, proving the analyser or system meets specification. Distinct from SAT, and not part of a Service Upsell. |
