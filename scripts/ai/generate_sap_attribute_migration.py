#!/usr/bin/env python3
"""
Generate a Revenue Cloud SFDMU plan from an approved SAP product attribute manifest.

The manifest is the authoritative, human-reviewed migration input. This generator is
deterministic: the same manifest always produces byte-identical artifacts.

Usage:
    python scripts/ai/generate_sap_attribute_migration.py \
        --manifest datasets/sap/servomex-07930b1/manifest.yaml

Options:
    --manifest PATH      Approved YAML manifest (required)
    --output-dir PATH    Where to write the plan (default: the manifest's plan.path)
    --report PATH        Conversion report path (default: <output-dir>/conversion-report.md)

Exit codes:
    0  Plan generated (warnings may be present)
    1  Usage or I/O error
    2  Manifest rejected by validation
"""

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - environment guard
    sys.stderr.write(
        "error: PyYAML is required. Install it with: python -m pip install PyYAML\n"
    )
    raise SystemExit(1)


API_VERSION = "66.0"

DISPOSITIONS = {"generated", "excluded", "deferred", "superseded", "source-control"}
GENERATED_DATA_TYPES = {"Picklist", "Text", "Number", "Checkbox", "Date", "DateTime"}

# Raw SAP option codes are reused across characteristics, so they can never be
# Revenue Cloud record codes on their own.
AMBIGUOUS_RAW_CODE = re.compile(r"^[A-Za-z0-9]{1,4}$")

ASCII_SUBSTITUTIONS = {
    "\u00b0": " deg ",
    "\u2013": "-",
    "\u2014": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u00b3": "3",
    "\u00b2": "2",
    "\u00b5": "u",
    "\u2264": "<=",
    "\u2265": ">=",
    "\u00a0": " ",
}


class ManifestError(Exception):
    """Raised when the manifest cannot produce Revenue Cloud records."""


def ascii_normalize(text):
    """Return an ASCII-safe operational value. Exact source text stays in the manifest."""
    if text is None:
        return ""
    value = str(text)
    for source_char, replacement in ASCII_SUBSTITUTIONS.items():
        value = value.replace(source_char, replacement)
    value = value.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", value).strip()


def developer_name(identifier):
    name = re.sub(r"[^A-Za-z0-9_]", "_", str(identifier))
    if not name or not name[0].isalpha():
        name = "X" + name
    return re.sub(r"_+", "_", name)[:80]


def qualify(*parts):
    return "-".join(str(part).strip() for part in parts if str(part).strip())


# ---------------------------------------------------------------------------
# Manifest reading and validation
# ---------------------------------------------------------------------------


def load_manifest(path):
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"error: cannot read manifest {path}: {exc}")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ManifestError(f"{path}: manifest must be a YAML mapping")
    return data


def require(mapping, key, context):
    if key not in mapping or mapping[key] in (None, ""):
        raise ManifestError(f"{context}: missing required key '{key}'")
    return mapping[key]


def validate_approval(manifest):
    approval = manifest.get("approval")
    if not isinstance(approval, dict) or approval.get("approved") is not True:
        raise ManifestError(
            "approval: manifest is not approved. Set approval.approved: true "
            "with approval.approved_by and approval.approved_on after human review."
        )
    require(approval, "approved_by", "approval")
    require(approval, "approved_on", "approval")


def validate_node(node, context):
    require(node, "id", context)
    require(node, "label", context)
    disposition = require(node, "disposition", context)
    if disposition not in DISPOSITIONS:
        raise ManifestError(
            f"{context}: unknown disposition '{disposition}'. "
            f"Expected one of {sorted(DISPOSITIONS)}"
        )
    provenance = node.get("source")
    if not isinstance(provenance, dict) or not provenance.get("text"):
        raise ManifestError(f"{context}: missing source.text provenance")
    if provenance.get("page") is None:
        raise ManifestError(f"{context}: missing source.page provenance")
    return disposition


def validate_values(node, context):
    for value_index, value in enumerate(node.get("values") or []):
        value_context = f"{context}.values[{value_index}]"
        require(value, "code", value_context)
        require(value, "label", value_context)
        value_disposition = value.get("disposition", "generated")
        if value_disposition not in {"generated", "excluded"}:
            raise ManifestError(
                f"{value_context}: value disposition must be 'generated' or 'excluded'"
            )
        if value_disposition == "excluded" and not value.get("disposition_reason"):
            raise ManifestError(f"{value_context}: excluded values need a reason")


def validate(manifest):
    """Validate the manifest and return (picklists, categories, characteristics) index maps."""
    validate_approval(manifest)

    source = manifest.get("source")
    if not isinstance(source, dict):
        raise ManifestError("source: missing source block")
    for key in ("system", "document", "sap_product", "sap_class"):
        require(source, key, "source")

    target = manifest.get("target")
    if not isinstance(target, dict):
        raise ManifestError("target: missing target block")
    require(target, "product_sku", "target")

    plan = manifest.get("plan")
    if not isinstance(plan, dict):
        raise ManifestError("plan: missing plan block")
    require(plan, "path", "plan")

    # A source node may hold exactly one disposition, so ids are unique across kinds.
    dispositioned = {}

    def claim(node, kind, context):
        previous = dispositioned.get(node["id"])
        if previous:
            raise ManifestError(
                f"{context}: duplicate source node id '{node['id']}' "
                f"(already dispositioned as a {previous})"
            )
        dispositioned[node["id"]] = kind

    picklists = {}
    for index, node in enumerate(manifest.get("picklists") or []):
        context = f"picklists[{index}] ({node.get('id', '?')})"
        disposition = validate_node(node, context)
        claim(node, "picklist", context)
        picklists[node["id"]] = node
        validate_values(node, context)
        if disposition == "generated" and not [
            value
            for value in (node.get("values") or [])
            if value.get("disposition", "generated") == "generated"
        ]:
            raise ManifestError(f"{context}: shared picklists need retained values")

    categories = {}
    for index, node in enumerate(manifest.get("categories") or []):
        context = f"categories[{index}] ({node.get('id', '?')})"
        validate_node(node, context)
        claim(node, "category", context)
        categories[node["id"]] = node

    characteristics = {}
    for index, node in enumerate(manifest.get("characteristics") or []):
        context = f"characteristics[{index}] ({node.get('id', '?')})"
        disposition = validate_node(node, context)
        claim(node, "characteristic", context)
        characteristics[node["id"]] = node

        if disposition == "superseded":
            superseded_by = node.get("superseded_by")
            if not superseded_by:
                raise ManifestError(f"{context}: superseded nodes need 'superseded_by'")
        if disposition != "generated":
            if node.get("values"):
                raise ManifestError(
                    f"{context}: only generated characteristics may declare values"
                )
            continue

        data_type = require(node, "type", context)
        if data_type not in GENERATED_DATA_TYPES:
            raise ManifestError(
                f"{context}: unknown type '{data_type}'. "
                f"Expected one of {sorted(GENERATED_DATA_TYPES)}"
            )
        category_id = require(node, "category", context)
        if category_id not in categories:
            raise ManifestError(f"{context}: unknown category '{category_id}'")
        if categories[category_id]["disposition"] != "generated":
            raise ManifestError(
                f"{context}: category '{category_id}' is not generated"
            )

        shared = node.get("picklist")
        if shared:
            if data_type != "Picklist":
                raise ManifestError(
                    f"{context}: only picklist characteristics may reference a shared "
                    f"picklist. Set type: Picklist, or drop 'picklist'."
                )
            if node.get("values"):
                raise ManifestError(
                    f"{context}: a characteristic referencing shared picklist '{shared}' "
                    f"may not also declare values"
                )
            if shared not in picklists:
                raise ManifestError(f"{context}: unknown picklist '{shared}'")
            if picklists[shared]["disposition"] != "generated":
                raise ManifestError(f"{context}: picklist '{shared}' is not generated")

        values = [
            value
            for value in (node.get("values") or [])
            if value.get("disposition", "generated") == "generated"
        ]
        if data_type == "Picklist" and not values and not shared:
            raise ManifestError(f"{context}: picklist characteristics need retained values")
        if data_type != "Picklist" and node.get("values"):
            raise ManifestError(
                f"{context}: only picklist characteristics may declare values. "
                f"Set type: Picklist, or drop the values from this '{data_type}' characteristic."
            )
        validate_values(node, context)

    for node in characteristics.values():
        if node["disposition"] == "superseded":
            replacement = node["superseded_by"]
            if replacement not in characteristics:
                raise ManifestError(
                    f"characteristics ({node['id']}): superseded_by '{replacement}' is not a known characteristic"
                )

    return picklists, categories, characteristics


# ---------------------------------------------------------------------------
# Record building
# ---------------------------------------------------------------------------


def retained_values(characteristic):
    return [
        value
        for value in (characteristic.get("values") or [])
        if value.get("disposition", "generated") == "generated"
    ]


def build_records(manifest, picklists, categories, characteristics):
    source = manifest["source"]
    system = source["system"]
    sap_class = source["sap_class"]
    sku = manifest["target"]["product_sku"]
    prefix = qualify(system, sap_class)

    generated_categories = [
        node for node in categories.values() if node["disposition"] == "generated"
    ]
    generated_characteristics = [
        node for node in characteristics.values() if node["disposition"] == "generated"
    ]

    tables = {name: [] for name in OBJECT_ORDER}
    warnings = []

    def emit_picklist(owner_id, label, description, values):
        """Write one picklist and its permitted values, and return its code."""
        picklist_code = qualify(prefix, owner_id, "PL")
        tables["AttributePicklist"].append(
            {
                "Code": picklist_code,
                "Name": f"{label} ({owner_id})",
                "DataType": "Text",
                "Description": ascii_normalize(description),
                "Status": "Active",
            }
        )
        for sequence, value in enumerate(values, start=1):
            value_label = ascii_normalize(value["label"])
            tables["AttributePicklistValue"].append(
                {
                    "Code": qualify(prefix, owner_id, value["code"]),
                    "Name": value_label,
                    "DisplayValue": value_label,
                    "Value": value_label,
                    "Abbreviation": str(value["code"]),
                    "Picklist.Code": picklist_code,
                    "Sequence": sequence,
                    "IsDefault": "true" if len(values) == 1 else "false",
                    "Status": "Active",
                }
            )
        return picklist_code

    shared_picklist_codes = {}
    for shared in sorted(
        (node for node in picklists.values() if node["disposition"] == "generated"),
        key=lambda node: node["id"],
    ):
        shared_picklist_codes[shared["id"]] = emit_picklist(
            shared["id"],
            ascii_normalize(shared["label"]),
            shared.get(
                "description", f"Shared permitted-value set {shared['id']}"
            ),
            retained_values(shared),
        )

    classification_code = prefix
    tables["ProductClassification"].append(
        {
            "Code": classification_code,
            "Name": ascii_normalize(
                manifest["target"].get("product_classification_name") or sap_class
            ),
            "ParentProductClassification.Code": "",
            "Status": "Active",
        }
    )

    for category in sorted(generated_categories, key=lambda node: node["id"]):
        tables["AttributeCategory"].append(
            {
                "Code": qualify(prefix, category["id"]),
                "Name": ascii_normalize(category["label"]),
                "Description": ascii_normalize(category.get("description", "")),
            }
        )

    for characteristic in sorted(generated_characteristics, key=lambda node: node["id"]):
        char_id = characteristic["id"]
        attribute_code = qualify(prefix, char_id)
        category_code = qualify(prefix, characteristic["category"])
        label = ascii_normalize(characteristic["label"])
        shared_id = characteristic.get("picklist")
        values = retained_values(picklists[shared_id] if shared_id else characteristic)
        is_single_value = characteristic["type"] == "Picklist" and len(values) == 1

        picklist_code = ""
        if shared_id:
            picklist_code = shared_picklist_codes[shared_id]
        elif characteristic["type"] == "Picklist":
            picklist_code = emit_picklist(
                char_id,
                label,
                f"Permitted-value set for SAP characteristic {char_id}",
                values,
            )

        tables["AttributeDefinition"].append(
            {
                "Code": attribute_code,
                "Name": f"{label} ({char_id})",
                "Label": label,
                "DeveloperName": developer_name(char_id),
                "DataType": characteristic["type"],
                "Description": ascii_normalize(characteristic.get("description", "")),
                "IsActive": "true",
                "IsRequired": "true" if is_single_value else "false",
                "Picklist.Code": picklist_code,
                "SourceSystemIdentifier": char_id,
                "DefaultHelpText": ascii_normalize(characteristic.get("help_text", "")),
            }
        )

        tables["AttributeCategoryAttribute"].append(
            {
                "$$AttributeCategory.Code$AttributeDefinition.Code": (
                    f"{category_code};{attribute_code}"
                ),
                "AttributeCategory.Code": category_code,
                "AttributeDefinition.Code": attribute_code,
            }
        )

        default_value = ""
        if is_single_value:
            default_value = ascii_normalize(values[0]["label"])
        elif characteristic.get("default_value"):
            default_value = ascii_normalize(characteristic["default_value"])

        sequence = characteristic.get("sequence") or 0
        assignment_name = attribute_code
        policy = {
            "AttributeNameOverride": label,
            "DefaultValue": default_value,
            "IsHidden": "false",
            "IsPriceImpacting": "false",
            "IsReadOnly": "true" if is_single_value else "false",
            "IsRequired": "true" if is_single_value else "false",
            "Sequence": sequence,
            "Status": "Active",
        }

        tables["ProductClassificationAttr"].append(
            {
                "Name": assignment_name,
                "ProductClassification.Code": classification_code,
                "AttributeCategory.Code": category_code,
                "AttributeDefinition.Code": attribute_code,
                **policy,
            }
        )

        tables["ProductAttributeDefinition"].append(
            {
                "Name": qualify(attribute_code, sku),
                "Product2.StockKeepingUnit": sku,
                "ProductClassificationAttribute.Name": assignment_name,
                "AttributeCategory.Code": category_code,
                "AttributeDefinition.Code": attribute_code,
                **policy,
            }
        )

    tables["Product2"].append(
        {"StockKeepingUnit": sku, "BasedOn.Code": classification_code}
    )

    duplicates = find_duplicate_codes(tables)
    if duplicates:
        raise ManifestError(
            "duplicate generated codes: " + ", ".join(sorted(duplicates))
        )

    check_raw_code_identity(tables)
    check_plan_integrity(tables)

    for entry in manifest.get("unresolved") or []:
        warnings.append(
            f"{entry.get('id', 'unresolved')}: {entry.get('reason', 'unresolved source logic')}"
        )

    return tables, warnings


IDENTITY_FIELD = {
    "AttributePicklist": "Code",
    "AttributePicklistValue": "Code",
    "AttributeDefinition": "Code",
    "AttributeCategory": "Code",
    "AttributeCategoryAttribute": "$$AttributeCategory.Code$AttributeDefinition.Code",
    "ProductClassification": "Code",
    "ProductClassificationAttr": "Name",
    "Product2": "StockKeepingUnit",
    "ProductAttributeDefinition": "Name",
}


def find_duplicate_codes(tables):
    duplicates = set()
    for object_name, rows in tables.items():
        seen = set()
        field = IDENTITY_FIELD[object_name]
        for row in rows:
            identity = row[field]
            if identity in seen:
                duplicates.add(f"{object_name}.{field}={identity}")
            seen.add(identity)
    return duplicates


# Product2 is matched on the customer's real SKU, which the generator never mints.
RAW_CODE_SCAN = {
    "AttributePicklist": ["Code"],
    "AttributePicklistValue": ["Code"],
    "AttributeDefinition": ["Code", "DeveloperName"],
    "AttributeCategory": ["Code"],
    "ProductClassification": ["Code"],
    "ProductClassificationAttr": ["Name"],
    "ProductAttributeDefinition": ["Name"],
}


def check_raw_code_identity(tables):
    """Reject minted identities that are still bare SAP codes."""
    offenders = set()
    for object_name, fields in RAW_CODE_SCAN.items():
        for row in tables[object_name]:
            for field in fields:
                identity = str(row.get(field, ""))
                if AMBIGUOUS_RAW_CODE.match(identity):
                    offenders.add(f"{object_name}.{field}={identity}")
    if offenders:
        raise ManifestError(
            "ambiguous raw SAP code used directly as a Revenue Cloud record identity: "
            + ", ".join(sorted(offenders))
            + ". Raw SAP codes repeat across characteristics; give the source node a "
            "longer, source-specific id."
        )


def check_plan_integrity(tables):
    """Reject a record chain with a broken link before it reaches an org."""
    picklists = {row["Code"] for row in tables["AttributePicklist"]}
    categories = {row["Code"] for row in tables["AttributeCategory"]}
    classifications = {row["Code"] for row in tables["ProductClassification"]}
    definitions = {row["Code"] for row in tables["AttributeDefinition"]}
    assignments = {row["Name"] for row in tables["ProductClassificationAttr"]}

    def require_parent(object_name, row, field, identity, known, parent_name):
        if row[field] not in known:
            raise ManifestError(
                f"{object_name} '{row[identity]}': {parent_name} "
                f"'{row[field]}' is not generated by this plan"
            )

    for row in tables["AttributePicklistValue"]:
        require_parent(
            "AttributePicklistValue", row, "Picklist.Code", "Code", picklists, "picklist"
        )

    for row in tables["AttributeDefinition"]:
        if row["DataType"] == "Picklist" and row["Picklist.Code"] not in picklists:
            raise ManifestError(
                f"AttributeDefinition '{row['Code']}': picklist attribute has no picklist"
            )

    referenced = {row["Picklist.Code"] for row in tables["AttributeDefinition"]}
    for row in tables["AttributePicklist"]:
        if row["Code"] not in referenced:
            raise ManifestError(
                f"AttributePicklist '{row['Code']}': no attribute definition references "
                "this picklist. Point a generated characteristic at it, or stop "
                "generating it."
            )

    for row in tables["AttributeCategoryAttribute"]:
        identity = "$$AttributeCategory.Code$AttributeDefinition.Code"
        require_parent(
            "AttributeCategoryAttribute", row, "AttributeCategory.Code", identity,
            categories, "attribute category",
        )
        require_parent(
            "AttributeCategoryAttribute", row, "AttributeDefinition.Code", identity,
            definitions, "attribute definition",
        )

    for row in tables["ProductClassificationAttr"]:
        require_parent(
            "ProductClassificationAttr", row, "ProductClassification.Code", "Name",
            classifications, "product classification",
        )
        require_parent(
            "ProductClassificationAttr", row, "AttributeDefinition.Code", "Name",
            definitions, "attribute definition",
        )

    for row in tables["ProductAttributeDefinition"]:
        require_parent(
            "ProductAttributeDefinition", row, "ProductClassificationAttribute.Name",
            "Name", assignments, "classification attribute assignment",
        )

    check_single_value_policy(tables)


def check_single_value_policy(tables):
    """A sole permitted value leaves the buyer no choice, so it must be locked in."""
    values_by_picklist = {}
    for row in tables["AttributePicklistValue"]:
        values_by_picklist.setdefault(row["Picklist.Code"], []).append(row)

    for definition in tables["AttributeDefinition"]:
        values = values_by_picklist.get(definition["Picklist.Code"], [])
        if len(values) != 1:
            continue
        sole = values[0]
        if sole["IsDefault"] != "true":
            raise ManifestError(
                f"AttributePicklistValue '{sole['Code']}': sole permitted value "
                "must be the picklist default"
            )
        for object_name in ("ProductClassificationAttr", "ProductAttributeDefinition"):
            for row in tables[object_name]:
                if row["AttributeDefinition.Code"] != definition["Code"]:
                    continue
                if (
                    row["IsRequired"] != "true"
                    or row["IsReadOnly"] != "true"
                    or row["DefaultValue"] != sole["Value"]
                ):
                    raise ManifestError(
                        f"{object_name} '{row['Name']}': single-value attribute must be "
                        f"required, read-only, and defaulted to '{sole['Value']}'"
                    )


# ---------------------------------------------------------------------------
# SFDMU plan rendering
# ---------------------------------------------------------------------------

OBJECT_ORDER = [
    "AttributePicklist",
    "AttributePicklistValue",
    "AttributeDefinition",
    "AttributeCategory",
    "AttributeCategoryAttribute",
    "ProductClassification",
    "ProductClassificationAttr",
    "Product2",
    "ProductAttributeDefinition",
]

CSV_COLUMNS = {
    "AttributePicklist": ["Code", "Name", "DataType", "Description", "Status"],
    "AttributePicklistValue": [
        "Code",
        "Name",
        "DisplayValue",
        "Value",
        "Abbreviation",
        "Picklist.Code",
        "Sequence",
        "IsDefault",
        "Status",
    ],
    "AttributeDefinition": [
        "Code",
        "Name",
        "Label",
        "DeveloperName",
        "DataType",
        "Description",
        "IsActive",
        "IsRequired",
        "Picklist.Code",
        "SourceSystemIdentifier",
        "DefaultHelpText",
    ],
    "AttributeCategory": ["Code", "Name", "Description"],
    "AttributeCategoryAttribute": [
        "$$AttributeCategory.Code$AttributeDefinition.Code",
        "AttributeCategory.Code",
        "AttributeDefinition.Code",
    ],
    "ProductClassification": [
        "Code",
        "Name",
        "ParentProductClassification.Code",
        "Status",
    ],
    "ProductClassificationAttr": [
        "Name",
        "ProductClassification.Code",
        "AttributeCategory.Code",
        "AttributeDefinition.Code",
        "AttributeNameOverride",
        "DefaultValue",
        "IsHidden",
        "IsPriceImpacting",
        "IsReadOnly",
        "IsRequired",
        "Sequence",
        "Status",
    ],
    "Product2": ["StockKeepingUnit", "BasedOn.Code"],
    "ProductAttributeDefinition": [
        "Name",
        "Product2.StockKeepingUnit",
        "ProductClassificationAttribute.Name",
        "AttributeCategory.Code",
        "AttributeDefinition.Code",
        "AttributeNameOverride",
        "DefaultValue",
        "IsHidden",
        "IsPriceImpacting",
        "IsReadOnly",
        "IsRequired",
        "Sequence",
        "Status",
    ],
}


def export_objects(sku):
    """SFDMU object definitions in parent-before-child order."""
    return [
        {
            "query": "SELECT Code, DataType, Description, Id, Name, Status "
            "FROM AttributePicklist ORDER BY Code ASC",
            "operation": "Upsert",
            "externalId": "Code",
        },
        {
            "query": "SELECT Abbreviation, Code, DisplayValue, Id, IsDefault, Name, "
            "PicklistId, Sequence, Status, Value FROM AttributePicklistValue "
            "ORDER BY Code ASC",
            "operation": "Upsert",
            "externalId": "Code",
        },
        {
            "query": "SELECT Code, DataType, DefaultHelpText, Description, DeveloperName, "
            "Id, IsActive, IsRequired, Label, Name, PicklistId, SourceSystemIdentifier "
            "FROM AttributeDefinition ORDER BY Code ASC",
            "operation": "Upsert",
            "externalId": "Code",
        },
        {
            "query": "SELECT Code, Description, Id, Name FROM AttributeCategory "
            "ORDER BY Code ASC",
            "operation": "Upsert",
            "externalId": "Code",
        },
        {
            "query": "SELECT AttributeCategoryId, AttributeCategory.Code, AttributeDefinitionId, "
            "AttributeDefinition.Code, Id FROM AttributeCategoryAttribute "
            "ORDER BY AttributeCategory.Code ASC, AttributeDefinition.Code ASC",
            "operation": "Upsert",
            "externalId": "AttributeCategory.Code;AttributeDefinition.Code",
        },
        {
            "query": "SELECT Code, Id, Name, ParentProductClassificationId, Status "
            "FROM ProductClassification ORDER BY Code ASC",
            "operation": "Upsert",
            "externalId": "Code",
        },
        {
            "query": "SELECT AttributeCategoryId, AttributeDefinitionId, AttributeNameOverride, "
            "DefaultValue, Id, IsHidden, IsPriceImpacting, IsReadOnly, IsRequired, Name, "
            "ProductClassificationId, Sequence, Status FROM ProductClassificationAttr "
            "ORDER BY Name ASC",
            "operation": "Upsert",
            "externalId": "Name",
        },
        {
            "query": "SELECT BasedOnId, Id, StockKeepingUnit FROM Product2 "
            f"WHERE StockKeepingUnit = '{sku}' ORDER BY StockKeepingUnit ASC",
            "operation": "Update",
            "externalId": "StockKeepingUnit",
        },
        {
            "query": "SELECT AttributeCategoryId, AttributeDefinitionId, AttributeNameOverride, "
            "DefaultValue, Id, IsHidden, IsPriceImpacting, IsReadOnly, IsRequired, Name, "
            "Product2Id, ProductClassificationAttributeId, Sequence, Status "
            "FROM ProductAttributeDefinition ORDER BY Name ASC",
            "operation": "Upsert",
            "externalId": "Name",
        },
    ]


def render_json(data):
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def render_csv(object_name, rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=CSV_COLUMNS[object_name],
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in CSV_COLUMNS[object_name]})
    return buffer.getvalue()


def render_report(manifest, picklists, categories, characteristics, tables, warnings):
    source = manifest["source"]
    nodes = [("picklist", node) for node in picklists.values()]
    nodes += [("category", node) for node in categories.values()]
    nodes += [("characteristic", node) for node in characteristics.values()]
    lines = [
        "# SAP Product Attribute Conversion Report",
        "",
        "Generated by `scripts/ai/generate_sap_attribute_migration.py` from the approved manifest.",
        "",
        "| Field | Value |",
        "|-------|-------|",
        f"| Source system | {source['system']} |",
        f"| Source document | {source['document']} |",
        f"| SAP Product | {source['sap_product']} |",
        f"| SAP Class | {source['sap_class']} |",
        f"| Manifest revision | {manifest.get('revision', 'unversioned')} |",
        f"| Approved by | {manifest['approval']['approved_by']} |",
        f"| Approved on | {manifest['approval']['approved_on']} |",
        "",
        "## Generated Revenue Cloud Records",
        "",
        "| Object | Records |",
        "|--------|---------|",
    ]
    for object_name in OBJECT_ORDER:
        lines.append(f"| {object_name} | {len(tables[object_name])} |")

    lines += [
        "",
        "## Disposition Summary",
        "",
        "Every curated source node counted once, by the disposition its reviewer approved.",
        "",
        "| Disposition | Nodes | Generates records |",
        "|-------------|-------|-------------------|",
    ]
    for disposition in sorted(DISPOSITIONS):
        count = sum(1 for _, node in nodes if node["disposition"] == disposition)
        generates = "yes" if disposition == "generated" else "no"
        lines.append(f"| `{disposition}` | {count} | {generates} |")
    lines.append(f"| **Total** | {len(nodes)} | |")

    lines += [
        "",
        "## Generated Attributes by Category",
        "",
        "Retained characteristics that reach the configurator, in source position "
        "within each category.",
    ]
    for category in sorted(
        (node for node in categories.values() if node["disposition"] == "generated"),
        key=lambda node: node["id"],
    ):
        members = sorted(
            (
                node
                for node in characteristics.values()
                if node["disposition"] == "generated"
                and node.get("category") == category["id"]
            ),
            key=lambda node: (node.get("sequence") or 0, node["id"]),
        )
        lines += [
            "",
            f"### {category['label']} (`{category['id']}`)",
            "",
            "| Sequence | Source ID | Attribute | Type | Permitted Values |",
            "|----------|-----------|-----------|------|------------------|",
        ]
        for node in members:
            shared = node.get("picklist")
            if shared:
                permitted = f"shared `{shared}`"
            elif node["type"] == "Picklist":
                permitted = str(len(retained_values(node)))
            else:
                permitted = "free entry"
            lines.append(
                f"| {node.get('sequence') or 0} | `{node['id']}` | {node['label']} "
                f"| {node['type']} | {permitted} |"
            )

    lines += [
        "",
        "## Deferred Source Nodes",
        "",
        "Source nodes held back until their Revenue Cloud data type is agreed. None of "
        "these generate Revenue Cloud rows.",
        "",
    ]
    deferred_nodes = sorted(
        (
            node
            for node in list(picklists.values())
            + list(categories.values())
            + list(characteristics.values())
            if node["disposition"] == "deferred"
        ),
        key=lambda node: node["id"],
    )
    if deferred_nodes:
        lines += [
            "| Source ID | Source Label | Reason |",
            "|-----------|--------------|--------|",
        ]
        for node in deferred_nodes:
            lines.append(
                f"| `{node['id']}` | {node['label']} | {node.get('disposition_reason', '')} |"
            )
    else:
        lines.append("None.")

    lines += [
        "",
        "## Source Node Dispositions",
        "",
        "Every node extracted from the source document appears exactly once, "
        "alongside any shared permitted-value set curated from them.",
        "",
        "| Source ID | Source Label | Kind | Disposition | Reason |",
        "|-----------|--------------|------|-------------|--------|",
    ]
    for kind, node in sorted(nodes, key=lambda item: item[1]["id"]):
        reason = node.get("disposition_reason", "")
        if node["disposition"] == "superseded":
            reason = f"superseded by {node['superseded_by']}" + (f" — {reason}" if reason else "")
        lines.append(
            f"| `{node['id']}` | {node['label']} | {kind} | {node['disposition']} | {reason} |"
        )

    excluded_values = []
    for node in list(picklists.values()) + list(characteristics.values()):
        for value in node.get("values") or []:
            if value.get("disposition", "generated") == "excluded":
                excluded_values.append((node["id"], value))
    lines += ["", "## Excluded Permitted Values", ""]
    if excluded_values:
        lines += [
            "| Characteristic | Value Code | Value Label | Reason |",
            "|----------------|------------|-------------|--------|",
        ]
        for char_id, value in sorted(excluded_values, key=lambda item: (item[0], str(item[1]["code"]))):
            lines.append(
                f"| `{char_id}` | `{value['code']}` | {value['label']} | {value['disposition_reason']} |"
            )
    else:
        lines.append("None.")

    lines += ["", "## Unresolved Source Logic", ""]
    if warnings:
        lines.append(
            "The source document indicates dependency and variant logic that it does not "
            "contain. No Revenue Cloud constraints were generated. Generated option "
            "combinations are **not** proven valid."
        )
        lines.append("")
        for warning in warnings:
            lines.append(f"- WARNING: {warning}")
    else:
        lines.append("None recorded.")

    lines.append("")
    return "\n".join(lines)


def render_plan_readme(manifest, tables, warnings):
    source = manifest["source"]
    sku = manifest["target"]["product_sku"]
    plan_path = manifest["plan"]["path"].rstrip("/")
    plan_name = plan_path.rsplit("/", 1)[-1]
    lines = [
        f"# {plan_name} Data Plan",
        "",
        f"Generated SFDMU plan converting SAP Class `{source['sap_class']}` "
        f"(`{source['document']}`) into Revenue Cloud attributes for Product `{sku}`.",
        "",
        "> **Generated artifact.** Do not edit by hand. Edit the approved manifest and",
        "> re-run `scripts/ai/generate_sap_attribute_migration.py`.",
        "",
        "## Prerequisites",
        "",
        f"- Product `{sku}` already exists in the target org. This plan never creates Products.",
        "- SFDMU v5.0.0+ (`sf sfdmu run`).",
        "",
        "## Load",
        "",
        "```bash",
        f"cci task run load_sfdmu_data -o pathtoexportjson {plan_path} --org <alias>",
        "```",
        "",
        "## Objects",
        "",
        "SFDMU loads the objects in this order, parent before child, so every lookup",
        "resolves against a record the previous step already wrote.",
        "",
        "| # | Object | Operation | External ID | Records |",
        "|---|--------|-----------|-------------|---------|",
    ]
    for index, (object_name, definition) in enumerate(
        zip(OBJECT_ORDER, export_objects(sku)), start=1
    ):
        lines.append(
            f"| {index} | {object_name} | {definition['operation']} | "
            f"`{definition['externalId']}` | {len(tables[object_name])} |"
        )

    lines += [
        "",
        "## Identity Strategy",
        "",
        "Generated codes are source-qualified as "
        f"`{source['system']}-{source['sap_class']}-<characteristic>[-<value>]` so that repeated",
        "raw SAP codes such as `A`, `X`, `1`, and `2` cannot collide globally. The raw SAP",
        "option code is preserved in `AttributePicklistValue.Abbreviation`, and the raw SAP",
        "characteristic id in `AttributeDefinition.SourceSystemIdentifier`.",
        "",
        "`ProductClassificationAttr` and `ProductAttributeDefinition` use generated `Name`",
        "values as direct external ids, because SFDMU v5 cannot reliably upsert on external",
        "ids composed only of relationship traversals. `AttributeCategoryAttribute` has no",
        "direct identity field, so it is the one object matched by traversal.",
        "",
        "## Safety",
        "",
        "- No object uses `deleteOldData`. Nothing in this plan deletes org records.",
        f"- `Product2` uses `Update`, scoped to `StockKeepingUnit = '{sku}'`, and writes only",
        "  `BasedOn.Code`. No other Product field is touched, and no Product is created.",
        "",
        "## Validate",
        "",
        "```bash",
        f"python scripts/validate_sfdmu_v5_datasets.py --dataset {plan_path}",
        "```",
        "",
        "## Warnings",
        "",
    ]
    if warnings:
        lines.append(
            "The source document references logic it does not contain. No Revenue Cloud "
            "constraints were generated, so loading this plan does **not** make every "
            "generated option combination valid."
        )
        lines.append("")
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("None recorded.")

    lines += [
        "",
        "See `conversion-report.md` for source node dispositions and unresolved source logic.",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def write_text(path, content):
    path.write_text(content, encoding="utf-8", newline="\n")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate a Revenue Cloud SFDMU plan from an approved SAP manifest."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Where to write the plan (default: the manifest's plan.path)",
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(args.manifest)
        picklists, categories, characteristics = validate(manifest)
        tables, warnings = build_records(manifest, picklists, categories, characteristics)
    except ManifestError as exc:
        sys.stderr.write(f"error: {args.manifest}: {exc}\n")
        return 2

    output_dir = args.output_dir or Path(manifest["plan"]["path"])
    output_dir.mkdir(parents=True, exist_ok=True)
    sku = manifest["target"]["product_sku"]

    write_text(
        output_dir / "export.json",
        render_json({"objects": export_objects(sku), "apiVersion": API_VERSION}),
    )
    for object_name in OBJECT_ORDER:
        write_text(
            output_dir / f"{object_name}.csv", render_csv(object_name, tables[object_name])
        )

    write_text(output_dir / "README.md", render_plan_readme(manifest, tables, warnings))

    report_path = args.report or (output_dir / "conversion-report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    write_text(
        report_path,
        render_report(manifest, picklists, categories, characteristics, tables, warnings),
    )

    total = sum(len(rows) for rows in tables.values())
    print(f"Generated {total} records across {len(OBJECT_ORDER)} objects in {output_dir}")
    print(f"Conversion report: {report_path}")
    for warning in warnings:
        print(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
