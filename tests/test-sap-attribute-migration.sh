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
echo "========================================="
echo "Passed: $PASS   Failed: $FAIL"
echo "========================================="
[[ $FAIL -eq 0 ]]
