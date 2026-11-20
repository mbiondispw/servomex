#!/usr/bin/env python3
"""
Generate the Option Adder matrix plan from an approved product attribute manifest.

Every `price` on a retained picklist value becomes one `Option_Adder__c` row:
product + attribute + value -> flat amount in the Option Adder currency. The
`Option_Adder_Matrix` decision table reads those rows, so a Price Adjustment
Matrix element can apply one adder per selected value and stack them. Design:
docs/features/option-adder-price-adjustment-matrix.md.

The manifest is validated exactly as generate_sap_attribute_migration.py
validates it (approval gate, provenance, price rules); this script only adds
the matrix output. It is deterministic: the same manifest always produces
byte-identical artifacts.

Usage:
    python scripts/ai/generate_option_adder_matrix.py \
        --manifest datasets/sap/servomex-05230a1/manifest.yaml

Options:
    --manifest PATH      Approved YAML manifest (required)
    --output-dir PATH    Where to write the plan
                         (default: <plan.path>-option-adder-matrix)

Exit codes:
    0  Plan generated
    1  Usage or I/O error
    2  Manifest rejected by validation
"""

import argparse
import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_sap_attribute_migration as attributes  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
ADDER_OBJECT = "Option_Adder__c"
ADDER_COLUMNS = [
    "Code__c",
    "Name",
    "Product__r.StockKeepingUnit",
    "Attribute_Definition__r.Code",
    "Attribute_Picklist_Value__r.Code",
    "CurrencyIsoCode",
    "Adjustment_Type__c",
    "Adjustment_Value__c",
    "Is_Active__c",
    "Source_Reference__c",
]

# A Price Adjustment Matrix adjustment is a discount: a positive Amount lowers
# the price. An Option Adder raises it, so its adjustment value is negative.
# The design doc's verification spike confirms this before wiring.
ADJUSTMENT_SIGN = -1


def build_adders(manifest, characteristics):
    """One row per priced retained value, attributes and values in manifest order."""
    priced = [
        node
        for node in characteristics.values()
        if node["disposition"] == "generated" and attributes.priced_values(node)
    ]
    if not priced:
        raise attributes.ManifestError(
            "no priced values: the Option Adder matrix needs at least one value with a price"
        )
    sku = manifest["target"]["product_sku"]
    currency = manifest["target"]["option_adders"]["currency"]
    prefix = attributes.code_prefix(manifest)
    rows = []
    for node in priced:
        attribute_code = attributes.qualify(prefix, node["id"])
        label = attributes.ascii_normalize(node["label"])
        for value in attributes.priced_values(node):
            value_code = attributes.qualify(prefix, node["id"], value["code"])
            price = value["price"]
            rows.append(
                {
                    "Code__c": attributes.qualify(value_code, sku, currency),
                    "Name": f"{label}: {attributes.ascii_normalize(value['label'])}"[:80],
                    "Product__r.StockKeepingUnit": sku,
                    "Attribute_Definition__r.Code": attribute_code,
                    "Attribute_Picklist_Value__r.Code": value_code,
                    "CurrencyIsoCode": currency,
                    "Adjustment_Type__c": "Amount",
                    "Adjustment_Value__c": attributes.format_amount(
                        ADJUSTMENT_SIGN * price["amount"]
                    ),
                    "Is_Active__c": "true",
                    "Source_Reference__c": source_reference(price["source"]),
                    # Not plan columns: the README shows the business view.
                    "_attribute": label,
                    "_value": attributes.ascii_normalize(value["label"]),
                    "_amount": attributes.format_amount(price["amount"]),
                }
            )
    return rows


def source_reference(source):
    """Workbook prices cite Sheet!Cell; SAP prices cite their page."""
    if source.get("cell"):
        return f"{source['sheet']}!{source['cell']}"
    return f"page {source['page']}"


def render_csv(columns, rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=columns, lineterminator="\n", quoting=csv.QUOTE_MINIMAL
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column, "") for column in columns})
    return buffer.getvalue()


def display_path(path):
    """Repo-relative where possible, so the README is the same whatever the caller's cwd."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def default_output_dir(manifest):
    return f"{manifest['plan']['path']}-option-adder-matrix"


def render_readme(manifest, manifest_path, rows):
    target = manifest["target"]
    currency = target["option_adders"]["currency"]
    attribute_count = len({row["Attribute_Definition__r.Code"] for row in rows})
    plan_dir = default_output_dir(manifest)
    lines = [
        f"# Option Adder matrix: {target.get('product_classification_name') or target['product_sku']} "
        f"({target['product_sku']})",
        "",
        "> Generated by `scripts/ai/generate_option_adder_matrix.py` from "
        f"`{display_path(manifest_path)}` (revision {manifest.get('revision', 'unknown')}). Do not edit by hand:",
        "> change the manifest and regenerate.",
        "",
        "**Not wired.** No pricing procedure or pricing recipe reads the `Option_Adder_Matrix`",
        "decision table yet, and it ships as Draft. Loading this plan changes no quote price.",
        "Design and wiring steps: `docs/features/option-adder-price-adjustment-matrix.md`.",
        "",
        "## What it loads",
        "",
        f"{len(rows)} Option Adders across {attribute_count} attributes, in {currency}. Each row is one",
        "`Option_Adder__c`: product + attribute + picklist value -> a flat amount. Every priced",
        "value is here, whether or not its attribute is price-impacting, because the Price",
        "Adjustment Matrix reads the line's selected values directly. The adjustment value is",
        "the negative of the adder: a matrix adjustment is a discount.",
        "",
        f"| Attribute | Value | Adder ({currency}) | Source |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(f"| {row['_attribute']} | {row['_value']} | {row['_amount']} | {row['Source_Reference__c']} |")
    lines += [
        "",
        "## Load",
        "",
        "Prerequisites:",
        "",
        f"1. The attribute plan `{manifest['plan']['path']}` is loaded, so the product, attribute",
        "   definitions and picklist values exist. This plan only reads them.",
        "2. The metadata bundle `unpackaged/post_option_adder_matrix` is deployed and its permission",
        "   set is assigned to the loading user:",
        "",
        "   ```bash",
        "   sf project deploy start --source-dir unpackaged/post_option_adder_matrix --target-org <sf-alias>",
        "   sf org assign permset --name Option_Adder_Matrix --target-org <sf-alias>",
        "   ```",
        "",
        "This project defines no data tasks. Run the `load_sfdmu_data` task from a checkout of",
        "the sibling `rlm-base-dev` CumulusCI project, pointed at this plan by absolute path:",
        "",
        "```bash",
        "cd <rlm-base-dev>",
        "cci task run load_sfdmu_data --org <cci-alias> \\",
        f"    -o pathtoexportjson <this-repo>/{plan_dir}",
        "```",
        "",
        "The task writes the org's credentials into `export.json` while it runs. Never commit it",
        "mid-load; restore it afterwards with",
        f"`git checkout -- {plan_dir}/export.json`.",
        "",
        "A decision table copies its rows only when refreshed, so the wiring ticket activates and",
        "refreshes `Option_Adder_Matrix` after this load.",
        "",
        "## Safety",
        "",
        "- `Option_Adder__c` is upserted on `Code__c`, a direct unique external id, so reruns",
        "  update rows and never duplicate them. No object uses `deleteOldData`.",
        "- `Product2`, `AttributeDefinition` and `AttributePicklistValue` are `Readonly`: the plan",
        "  only resolves lookups to them.",
        "- Retire an adder by setting `Is_Active__c` to false; the decision table reads active rows only.",
        "",
    ]
    return "\n".join(lines)


def parent_tables(rows):
    """The parents each matrix row looks up, as Readonly SFDMU sources (externalId only)."""
    return {
        "Product2": ("StockKeepingUnit", sorted({row["Product__r.StockKeepingUnit"] for row in rows})),
        "AttributeDefinition": ("Code", sorted({row["Attribute_Definition__r.Code"] for row in rows})),
        "AttributePicklistValue": (
            "Code",
            sorted({row["Attribute_Picklist_Value__r.Code"] for row in rows}),
        ),
    }


def export_plan(manifest):
    sku = manifest["target"]["product_sku"]
    prefix = attributes.code_prefix(manifest)
    return {
        "objects": [
            {
                "query": "SELECT Id, StockKeepingUnit FROM Product2 "
                f"WHERE StockKeepingUnit = '{sku}' ORDER BY StockKeepingUnit ASC",
                "operation": "Readonly",
                "externalId": "StockKeepingUnit",
            },
            {
                "query": "SELECT Code, Id FROM AttributeDefinition "
                f"WHERE Code LIKE '{prefix}-%' ORDER BY Code ASC",
                "operation": "Readonly",
                "externalId": "Code",
            },
            {
                "query": "SELECT Code, Id FROM AttributePicklistValue "
                f"WHERE Code LIKE '{prefix}-%' ORDER BY Code ASC",
                "operation": "Readonly",
                "externalId": "Code",
            },
            {
                "query": "SELECT Adjustment_Type__c, Adjustment_Value__c, Attribute_Definition__c, "
                "Attribute_Picklist_Value__c, Code__c, CurrencyIsoCode, Id, Is_Active__c, Name, "
                f"Product__c, Source_Reference__c FROM {ADDER_OBJECT} "
                f"WHERE Product__r.StockKeepingUnit = '{sku}' ORDER BY Code__c ASC",
                "operation": "Upsert",
                "externalId": "Code__c",
            },
        ],
        "apiVersion": attributes.API_VERSION,
        # Without this, SFDMU cannot resolve Parent.ExternalId columns in
        # Id-less CSVs and silently writes every lookup as null.
        "excludeIdsFromCSVFiles": "true",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate the Option Adder matrix plan from an approved manifest."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)

    try:
        manifest = attributes.load_manifest(args.manifest)
        _, _, characteristics = attributes.validate(manifest)
        rows = build_adders(manifest, characteristics)
    except attributes.ManifestError as exc:
        sys.stderr.write(f"error: {args.manifest}: {exc}\n")
        return 2

    output_dir = args.output_dir or Path(default_output_dir(manifest))
    output_dir.mkdir(parents=True, exist_ok=True)
    attributes.write_text(output_dir / "export.json", attributes.render_json(export_plan(manifest)))
    for object_name, (key, values) in parent_tables(rows).items():
        attributes.write_text(
            output_dir / f"{object_name}.csv",
            render_csv([key], [{key: value} for value in values]),
        )
    attributes.write_text(output_dir / f"{ADDER_OBJECT}.csv", render_csv(ADDER_COLUMNS, rows))
    attributes.write_text(output_dir / "README.md", render_readme(manifest, args.manifest, rows))
    print(f"Generated {len(rows)} Option Adders in {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
