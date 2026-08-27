#!/bin/bash
#
# CLI-level behavioral test for the SAP product attribute migration generator.
#
# The generator CLI is the only seam under test: fixture manifest in, generated
# artifacts out. Nothing here reaches into the generator's internal functions.
#
# Usage: tests/test-sap-attribute-migration.sh

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURES="$REPO_ROOT/tests/fixtures/sap-attribute-migration"
GENERATOR="$REPO_ROOT/scripts/ai/generate_sap_attribute_migration.py"

if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PYTHON="$REPO_ROOT/.venv/bin/python"
else
    PYTHON="${PYTHON:-python3}"
fi

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

PASS=0
FAIL=0

pass() { echo "  ok   $1"; PASS=$((PASS + 1)); }
fail() { echo "  FAIL $1"; FAIL=$((FAIL + 1)); }

assert_contains() {
    local file="$1" needle="$2" description="$3"
    if grep -qF -- "$needle" "$file"; then pass "$description"; else fail "$description"; fi
}

assert_absent() {
    local file="$1" needle="$2" description="$3"
    if grep -qF -- "$needle" "$file"; then fail "$description"; else pass "$description"; fi
}

echo "========================================="
echo "SAP product attribute migration generator"
echo "========================================="
echo "Python: $PYTHON"
echo ""

# --- Generation from an approved manifest ---------------------------------
echo "Test 1: approved manifest generates the full record chain"
RUN_A="$WORK_DIR/run-a"
"$PYTHON" "$GENERATOR" \
    --manifest "$FIXTURES/approved-tracer.yaml" \
    --output-dir "$RUN_A" >"$WORK_DIR/run-a.log" 2>&1
EXIT_CODE=$?

if [[ $EXIT_CODE -eq 0 ]]; then pass "exit code 0"; else fail "exit code 0 (got $EXIT_CODE)"; cat "$WORK_DIR/run-a.log"; fi

for artifact in export.json README.md conversion-report.md \
    AttributePicklist.csv AttributePicklistValue.csv AttributeDefinition.csv \
    AttributeCategory.csv AttributeCategoryAttribute.csv ProductClassification.csv \
    ProductClassificationAttr.csv Product2.csv ProductAttributeDefinition.csv; do
    if [[ -f "$RUN_A/$artifact" ]]; then pass "generated $artifact"; else fail "generated $artifact"; fi
done

echo ""
echo "Test 2: record relationships are source-qualified and connected"
assert_contains "$RUN_A/ProductClassification.csv" "SAP-CLASS_7930B" "ProductClassification uses the SAP class"
assert_contains "$RUN_A/AttributeCategory.csv" "SAP-CLASS_7930B-C7900_PART_HEADER,Analyser Base Config" "category derived from the section header"
assert_contains "$RUN_A/AttributeCategoryAttribute.csv" "SAP-CLASS_7930B-C7900_PART_HEADER;SAP-CLASS_7930B-C7900B_TPBASE" "attribute linked to its category"
assert_contains "$RUN_A/AttributeDefinition.csv" "SAP-CLASS_7930B-C7900B_TPBASE-PL,C7900B_TPBASE" "definition references its picklist and keeps the SAP source id"
assert_contains "$RUN_A/AttributePicklistValue.csv" "SAP-CLASS_7930B-C7900B_TPBASE-07931B1" "value code is source-qualified"
assert_contains "$RUN_A/AttributePicklistValue.csv" ",07931B1,SAP-CLASS_7930B-C7900B_TPBASE-PL" "raw SAP code retained in Abbreviation"
assert_contains "$RUN_A/ProductClassificationAttr.csv" "SAP-CLASS_7930B-C7900B_TPBASE,SAP-CLASS_7930B," "attribute assigned at classification level"
assert_contains "$RUN_A/ProductAttributeDefinition.csv" "SAP-CLASS_7930B-C7900B_TPBASE-07930B1,07930B1,SAP-CLASS_7930B-C7900B_TPBASE" "product binding backed by the classification assignment"

echo ""
echo "Test 3: single permitted value is required, read-only, and default"
assert_contains "$RUN_A/ProductAttributeDefinition.csv" "Type,Laser 3 Plus,false,false,true,true," "binding is defaulted, read-only, and required"
assert_contains "$RUN_A/AttributePicklistValue.csv" ",1,true,Active" "sole permitted value is the picklist default"

echo ""
echo "Test 4: the Product update is narrowly scoped"
PRODUCT_HEADER="$(head -1 "$RUN_A/Product2.csv")"
if [[ "$PRODUCT_HEADER" == "StockKeepingUnit,BasedOn.Code" ]]; then
    pass "Product2 columns limited to SKU identity and classification"
else
    fail "Product2 columns limited to SKU identity and classification (got: $PRODUCT_HEADER)"
fi
if [[ "$(wc -l <"$RUN_A/Product2.csv" | tr -d ' ')" == "2" ]]; then
    pass "exactly one Product row"
else
    fail "exactly one Product row"
fi
assert_contains "$RUN_A/export.json" '"operation": "Update"' "Product2 uses Update, never insert"

echo ""
echo "Test 5: the plan is non-destructive"
assert_absent "$RUN_A/export.json" "deleteOldData" "no deleteOldData anywhere in the plan"
assert_absent "$RUN_A/export.json" '"Delete"' "no Delete operation anywhere in the plan"

echo ""
echo "Test 6: the conversion report accounts for every source node"
for node in C7900_PART_HEADER C7900B_TPBASE C7900_TPBASE CMATERIAL_NUMBER C7900_DTP; do
    assert_contains "$RUN_A/conversion-report.md" "\`$node\`" "report lists $node"
done
assert_contains "$RUN_A/conversion-report.md" "superseded by C7900B_TPBASE" "supersession is traceable"
assert_contains "$RUN_A/conversion-report.md" "Duplicates Product identity." "exclusion reason is reported"
assert_contains "$RUN_A/conversion-report.md" "WARNING: CLASS_7930B-dependencies" "unresolved dependency logic is a warning"
assert_contains "$WORK_DIR/run-a.log" "WARNING: CLASS_7930B-dependencies" "unresolved dependency logic is reported on stdout"

echo ""
echo "Test 7: generation is byte-stable"
RUN_B="$WORK_DIR/run-b"
"$PYTHON" "$GENERATOR" \
    --manifest "$FIXTURES/approved-tracer.yaml" \
    --output-dir "$RUN_B" >/dev/null 2>&1
if diff -r "$RUN_A" "$RUN_B" >/dev/null 2>&1; then
    pass "repeated generation is byte-identical"
else
    fail "repeated generation is byte-identical"
    diff -r "$RUN_A" "$RUN_B" | head -20
fi

echo ""
echo "Test 8: an unapproved manifest is refused"
"$PYTHON" "$GENERATOR" \
    --manifest "$FIXTURES/unapproved-tracer.yaml" \
    --output-dir "$WORK_DIR/run-unapproved" >"$WORK_DIR/unapproved.log" 2>&1
EXIT_CODE=$?
if [[ $EXIT_CODE -eq 2 ]]; then pass "exit code 2"; else fail "exit code 2 (got $EXIT_CODE)"; fi
assert_contains "$WORK_DIR/unapproved.log" "manifest is not approved" "diagnostic explains the approval gate"
if [[ ! -f "$WORK_DIR/run-unapproved/export.json" ]]; then
    pass "no artifacts written for an unapproved manifest"
else
    fail "no artifacts written for an unapproved manifest"
fi

echo ""
echo "Test 9: incomplete or ambiguous manifests are refused with an actionable diagnostic"
run_rejection() {
    local fixture="$1" needle="$2" description="$3"
    local slug out_dir log
    slug="$(basename "$fixture" .yaml)"
    out_dir="$WORK_DIR/reject-$slug"
    log="$WORK_DIR/reject-$slug.log"

    "$PYTHON" "$GENERATOR" \
        --manifest "$FIXTURES/invalid/$fixture" \
        --output-dir "$out_dir" >"$log" 2>&1
    local code=$?

    if [[ $code -eq 2 ]]; then
        pass "$description (exit 2)"
    else
        fail "$description (exit 2, got $code)"
        head -5 "$log"
    fi
    assert_contains "$log" "$needle" "$description (diagnostic)"
    if [[ ! -d "$out_dir" ]]; then
        pass "$description (no artifacts written)"
    else
        fail "$description (no artifacts written)"
    fi
}

run_rejection missing-source-identifier.yaml "missing required key 'id'" \
    "a source node without its SAP identifier"
run_rejection missing-disposition.yaml "missing required key 'disposition'" \
    "a source node without a disposition"
run_rejection unknown-type.yaml "unknown type 'Lookup'" \
    "an unknown Revenue Cloud data type"
run_rejection missing-category.yaml "missing required key 'category'" \
    "a retained characteristic without a category"
run_rejection duplicate-generated-code.yaml "duplicate generated codes" \
    "two permitted values collapsing onto one generated code"
run_rejection picklist-without-values.yaml "picklist characteristics need retained values" \
    "a picklist attribute with no retained values"
run_rejection values-without-picklist.yaml "only picklist characteristics may declare values" \
    "permitted values with nowhere to live"
run_rejection ambiguous-raw-code.yaml "ambiguous raw SAP code" \
    "a raw SAP code used directly as a record identity"

echo ""
echo "Test 10: approved deferred and source-control nodes generate no Revenue Cloud rows"
RUN_DEFERRED="$WORK_DIR/run-deferred"
"$PYTHON" "$GENERATOR" \
    --manifest "$FIXTURES/deferred-nodes.yaml" \
    --output-dir "$RUN_DEFERRED" >"$WORK_DIR/run-deferred.log" 2>&1
EXIT_CODE=$?
if [[ $EXIT_CODE -eq 0 ]]; then pass "exit code 0"; else fail "exit code 0 (got $EXIT_CODE)"; cat "$WORK_DIR/run-deferred.log"; fi

for node in CAT_DEFERRED_HEADER CHAR_DEFERRED_RANGE CHAR_SOURCE_CONTROL_DTP; do
    assert_contains "$RUN_DEFERRED/conversion-report.md" "\`$node\`" "report accounts for $node"
    if grep -rqF -- "$node" "$RUN_DEFERRED"/*.csv; then
        fail "$node produces no Revenue Cloud rows"
    else
        pass "$node produces no Revenue Cloud rows"
    fi
done
assert_contains "$RUN_DEFERRED/AttributeDefinition.csv" "SAP-CLASS_7930B-CHAR_TYPE" "retained characteristic still generates"

echo ""
echo "Test 11: missing SAP dependency rules warn instead of generating constraints"
assert_contains "$WORK_DIR/run-deferred.log" "WARNING: CLASS_7930B-dependencies" "unresolved dependency logic warns on stdout"
assert_contains "$RUN_DEFERRED/conversion-report.md" "not** proven valid" "report states option combinations are unproven"
for constraint_object in ProductConfigurationRule ProductRelationshipType ProductConfigurationFlow ExpressionSet; do
    assert_absent "$RUN_DEFERRED/export.json" "$constraint_object" "no $constraint_object in the generated plan"
done

echo ""
echo "Test 12: the generated plan is internally complete"
column_values() {
    "$PYTHON" - "$1" "$2" <<'PY'
import csv, sys
with open(sys.argv[1], newline="") as handle:
    for row in csv.DictReader(handle):
        print(row[sys.argv[2]])
PY
}

assert_subset() {
    local child_file="$1" child_column="$2" parent_file="$3" parent_column="$4" description="$5"
    local missing
    if [[ ! -f "$child_file" || ! -f "$parent_file" ]]; then
        fail "$description (missing generated CSV)"
        return
    fi
    missing="$(comm -23 \
        <(column_values "$child_file" "$child_column" | grep -v '^$' | sort -u) \
        <(column_values "$parent_file" "$parent_column" | sort -u))"
    if [[ -z "$missing" ]]; then
        pass "$description"
    else
        fail "$description (dangling: $(echo "$missing" | tr '\n' ' '))"
    fi
}

assert_subset "$RUN_A/ProductAttributeDefinition.csv" "ProductClassificationAttribute.Name" \
    "$RUN_A/ProductClassificationAttr.csv" "Name" \
    "every product binding is backed by a classification attribute assignment"
assert_subset "$RUN_A/AttributeDefinition.csv" "Picklist.Code" \
    "$RUN_A/AttributePicklist.csv" "Code" \
    "every picklist attribute references a generated picklist"
assert_subset "$RUN_A/AttributePicklistValue.csv" "Picklist.Code" \
    "$RUN_A/AttributePicklist.csv" "Code" \
    "every permitted value belongs to a generated picklist"
assert_subset "$RUN_A/AttributeCategoryAttribute.csv" "AttributeCategory.Code" \
    "$RUN_A/AttributeCategory.csv" "Code" \
    "every category link references a generated category"
assert_subset "$RUN_A/ProductClassificationAttr.csv" "ProductClassification.Code" \
    "$RUN_A/ProductClassification.csv" "Code" \
    "every assignment references the generated classification"

echo ""
echo "========================================="
echo "Passed: $PASS   Failed: $FAIL"
echo "========================================="
[[ $FAIL -eq 0 ]]
