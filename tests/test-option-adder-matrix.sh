#!/bin/bash
#
# CLI-level behavioral test for the Option Adder matrix generator (#46).
#
# The generator CLI is the only seam under test: fixture manifest in, generated
# plan out. Nothing here reaches into the generator's internal functions.
#
# Usage: tests/test-option-adder-matrix.sh

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURES="$REPO_ROOT/tests/fixtures/option-adder-matrix"
SAP_FIXTURES="$REPO_ROOT/tests/fixtures/sap-attribute-migration"
GENERATOR="$REPO_ROOT/scripts/ai/generate_option_adder_matrix.py"

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
    if grep -qF -- "$needle" "$file" 2>/dev/null; then pass "$description"; else fail "$description"; fi
}

assert_absent() {
    local file="$1" needle="$2" description="$3"
    if grep -qF -- "$needle" "$file" 2>/dev/null; then fail "$description"; else pass "$description"; fi
}

assert_equals() {
    local actual="$1" expected="$2" description="$3"
    if [[ "$actual" == "$expected" ]]; then
        pass "$description"
    else
        fail "$description (expected '$expected', got '$actual')"
    fi
}

csv_column() {
    "$PYTHON" -c 'import csv, sys; [print(row[sys.argv[2]]) for row in csv.DictReader(open(sys.argv[1]))]' "$1" "$2" 2>/dev/null
}

echo "========================================="
echo "Option Adder matrix generator"
echo "========================================="
echo "Python: $PYTHON"
echo ""

echo "Test 1: an approved manifest generates one matrix row per priced value"
RUN_A="$WORK_DIR/run-a"
"$PYTHON" "$GENERATOR" \
    --manifest "$FIXTURES/approved-stacking.yaml" \
    --output-dir "$RUN_A" >"$WORK_DIR/run-a.log" 2>&1
EXIT_CODE=$?
if [[ $EXIT_CODE -eq 0 ]]; then pass "exit code 0"; else fail "exit code 0 (got $EXIT_CODE)"; cat "$WORK_DIR/run-a.log"; fi

MATRIX="$RUN_A/Option_Adder__c.csv"
assert_equals "$(head -1 "$MATRIX" 2>/dev/null)" \
    "Code__c,Name,Product__r.StockKeepingUnit,Attribute_Definition__r.Code,Attribute_Picklist_Value__r.Code,CurrencyIsoCode,Adjustment_Type__c,Adjustment_Value__c,Is_Active__c,Source_Reference__c" \
    "matrix columns are the Option_Adder__c fields"
assert_contains "$MATRIX" \
    "SMX-05230A1-PRINTER-1-05230A1-GBP,Printer: Supplied,05230A1,SMX-05230A1-PRINTER,SMX-05230A1-PRINTER-1,GBP,Amount,-1521,true,Product Config and Pricing!F41" \
    "Printer Supplied adds GBP 1,521 keyed on product, attribute and value, citing F41"

echo ""
echo "Test 2: every priced attribute is in the matrix, price-impacting or not"
assert_contains "$MATRIX" \
    "SMX-05230A1-TRANSPORT_CASE-1-05230A1-GBP,Transport Case: Supplied,05230A1,SMX-05230A1-TRANSPORT_CASE,SMX-05230A1-TRANSPORT_CASE-1,GBP,Amount,-806,true,Product Config and Pricing!F71" \
    "Transport Case Supplied (not price-impacting) adds GBP 806 as its own row"
assert_contains "$MATRIX" "SMX-05230A1-SIDE_PANEL-2-05230A1-GBP,Side Panel Accessories: Flow Meter + Valve" \
    "Flow Meter + Valve has a row"
assert_contains "$MATRIX" ",GBP,Amount,-947.5,true,Product Config and Pricing!F54" \
    "a decimal workbook price keeps its pence"
assert_absent "$MATRIX" "SMX-05230A1-SIDE_PANEL-0" "the unpriced added None has no row"
assert_absent "$MATRIX" "SMX-05230A1-PRINTER-0" "unpriced Printer Not Supplied has no row"
assert_equals "$(tail -n +2 "$MATRIX" | wc -l | tr -d ' ')" "4" "four priced values give four rows"
assert_equals "$(csv_column "$MATRIX" Attribute_Picklist_Value__r.Code | sort -u | wc -l | tr -d ' ')" "4" \
    "the two 'Supplied' values resolve to distinct picklist values"

echo ""
echo "Test 3: the plan upserts the matrix on a direct key and only reads its parents"
EXPORT="$RUN_A/export.json"
PLAN_SHAPE="$("$PYTHON" -c '
import json, sys
plan = json.load(open(sys.argv[1]))
for obj in plan["objects"]:
    name = obj["query"].split(" FROM ")[1].split()[0]
    print(name, obj["operation"], obj["externalId"], obj.get("deleteOldData", False))
print("excludeIdsFromCSVFiles", plan.get("excludeIdsFromCSVFiles"))
' "$EXPORT" 2>&1)"
assert_equals "$PLAN_SHAPE" "Product2 Readonly StockKeepingUnit False
AttributeDefinition Readonly Code False
AttributePicklistValue Readonly Code False
Option_Adder__c Upsert Code__c False
excludeIdsFromCSVFiles true" "parents are Readonly, the matrix is a non-destructive Upsert on Code__c"
assert_contains "$EXPORT" "FROM Product2 WHERE StockKeepingUnit = '05230A1'" "Product2 read is scoped to the product"
assert_contains "$EXPORT" "FROM Option_Adder__c WHERE Product__r.StockKeepingUnit = '05230A1'" \
    "matrix query is scoped to the product"
assert_equals "$(cat "$RUN_A/Product2.csv" 2>/dev/null)" "StockKeepingUnit
05230A1" "Product2.csv names only the product"
assert_equals "$(cat "$RUN_A/AttributeDefinition.csv" 2>/dev/null)" "Code
SMX-05230A1-PRINTER
SMX-05230A1-SIDE_PANEL
SMX-05230A1-TRANSPORT_CASE" "AttributeDefinition.csv names only the priced attributes"
assert_equals "$(cat "$RUN_A/AttributePicklistValue.csv" 2>/dev/null)" "Code
SMX-05230A1-PRINTER-1
SMX-05230A1-SIDE_PANEL-2
SMX-05230A1-SIDE_PANEL-3
SMX-05230A1-TRANSPORT_CASE-1" "AttributePicklistValue.csv names only the priced values"

echo ""
echo "Test 4a: the plan README lists every adder with its source cell and says it is not wired"
README="$RUN_A/README.md"
assert_contains "$README" "| Transport Case | Supplied | 806 | Product Config and Pricing!F71 |" \
"README lists Transport Case Supplied at 806 from F71"
assert_contains "$README" "| Side Panel Accessories | Flow Meter | 947.5 | Product Config and Pricing!F54 |" \
"README keeps a decimal price"
assert_contains "$README" "4 Option Adders across 3 attributes" "README counts adders and attributes"
assert_contains "$README" "Not wired" "README says the matrix is not wired into pricing"
assert_contains "$README" "unpackaged/post_option_adder_matrix" "README names the metadata bundle to deploy first"

echo ""
echo "Test 4: manifests the matrix cannot come from are rejected and write nothing"
run_rejection() {
local fixture="$1" diagnostic="$2" description="$3"
local out="$WORK_DIR/reject-$(basename "$fixture" .yaml)"
"$PYTHON" "$GENERATOR" --manifest "$fixture" --output-dir "$out" >"$out.log" 2>&1
local code=$?
assert_equals "$code" "2" "$description: exit code 2"
assert_contains "$out.log" "$diagnostic" "$description: says why"
if [[ -e "$out" ]]; then fail "$description: no output written"; else pass "$description: no output written"; fi
}
run_rejection "$SAP_FIXTURES/unapproved-tracer.yaml" "manifest is not approved" "unapproved manifest"
run_rejection "$SAP_FIXTURES/approved-tracer.yaml" "no priced values" "manifest without prices"
run_rejection "$SAP_FIXTURES/invalid/priced-excluded-value.yaml" "only retained values may carry a price" \
"price on an excluded value"
run_rejection "$SAP_FIXTURES/invalid/price-without-cell.yaml" "missing source.cell provenance" \
"price without its workbook cell"

echo ""
echo "Test 5: the committed Mini MP plan is the generator's output for the approved manifest"
MANIFEST="$REPO_ROOT/datasets/sap/servomex-05230a1/manifest.yaml"
COMMITTED="$REPO_ROOT/datasets/sfdmu/servomex/en-US/servomex-minimp-05230a1-option-adder-matrix"
FRESH="$WORK_DIR/fresh"
"$PYTHON" "$GENERATOR" --manifest "$MANIFEST" --output-dir "$FRESH" >"$WORK_DIR/fresh.log" 2>&1
if diff -r "$COMMITTED" "$FRESH" >"$WORK_DIR/fresh.diff" 2>&1; then
pass "committed plan is byte-identical to a fresh generation"
else
fail "committed plan is byte-identical to a fresh generation"; head -20 "$WORK_DIR/fresh.diff"
fi
REAL="$COMMITTED/Option_Adder__c.csv"
assert_equals "$(csv_column "$REAL" Attribute_Definition__r.Code | sort -u | sed 's/^SMX-05230A1-//' | tr '\n' ' ')" \
"INLET_COUPLER MA_OUTPUT MEASUREMENT_1 MEASUREMENT_2 PRINTER PROBE_HOLDER SAMPLE_PROBE SIDE_PANEL_ACCESSORIES SUPPLY_POWER TRANSPORT_CASE " \
"all 10 priced attributes are in the matrix"
assert_equals "$(grep -c ',GBP,Amount,-1292,' "$REAL" 2>/dev/null)" "3" "each battery adds GBP 1,292"
assert_equals "$(grep -c ',GBP,Amount,-4750,' "$REAL" 2>/dev/null)" "8" "each CO2 range adds GBP 4,750 in either measurement"
for adder in "MEASUREMENT_1-1A,GBP,Amount,-4755" "MEASUREMENT_1-2,GBP,Amount,-7534" \
    "MA_OUTPUT-1,GBP,Amount,-587" "MA_OUTPUT-2,GBP,Amount,-1170" "INLET_COUPLER-2,GBP,Amount,-99" \
    "PRINTER-2,GBP,Amount,-1521" "SIDE_PANEL_ACCESSORIES-1,GBP,Amount,-1326" \
    "SIDE_PANEL_ACCESSORIES-2,GBP,Amount,-1054" "SIDE_PANEL_ACCESSORIES-3,GBP,Amount,-947" \
    "PROBE_HOLDER-1,GBP,Amount,-339" "PROBE_HOLDER-2,GBP,Amount,-467" \
    "SAMPLE_PROBE-2,GBP,Amount,-111" "SAMPLE_PROBE-3,GBP,Amount,-133" "TRANSPORT_CASE-2,GBP,Amount,-806"; do
    assert_contains "$REAL" "SMX-05230A1-$adder," "real plan prices $adder"
done

echo ""
echo "Test 6: the plan and the decision table use the fields the metadata bundle defines"
BUNDLE="$REPO_ROOT/unpackaged/post_option_adder_matrix"
FIELDS="$BUNDLE/objects/Option_Adder__c/fields"
for column in $(head -1 "$REAL" | tr ',' ' '); do
    case "$column" in Name|CurrencyIsoCode) continue ;; esac
    field="${column%%__r.*}"
    [[ "$field" != "$column" ]] && field="${field}__c"
    if [[ -f "$FIELDS/$field.field-meta.xml" ]]; then pass "plan column $column is field $field"; else fail "plan column $column is field $field"; fi
done
assert_contains "$FIELDS/Code__c.field-meta.xml" "<externalId>true</externalId>" "Code__c is an external id"
assert_contains "$FIELDS/Code__c.field-meta.xml" "<unique>true</unique>" "Code__c is unique, so reruns update"
TABLE="$BUNDLE/decisionTables/Option_Adder_Matrix.decisionTable-meta.xml"
assert_contains "$TABLE" "<sourceObject>Option_Adder__c</sourceObject>" "decision table reads Option_Adder__c"
for path in $(grep -o '<fieldPath>[^<]*</fieldPath>' "$TABLE" 2>/dev/null | sed 's/<[^>]*>//g'); do
    if [[ "$path" == CurrencyIsoCode || -f "$FIELDS/$path.field-meta.xml" ]]; then
        pass "decision table column $path is a field"
    else
        fail "decision table column $path is a field"
    fi
done
TABLE_SHAPE="$(grep -c '<usage>INPUT</usage>' "$TABLE" 2>/dev/null) inputs, $(grep -c '<usage>OUTPUT</usage>' "$TABLE" 2>/dev/null) outputs"
assert_equals "$TABLE_SHAPE" "3 inputs, 2 outputs" "keyed on product, picklist value and currency; returns type and value"
if [[ -d "$BUNDLE/expressionSetDefinition" || -d "$BUNDLE/pricingRecipes" ]]; then
    fail "bundle wires nothing into pricing"
else
    pass "bundle wires nothing into pricing"
fi

echo ""
echo "========================================="
echo "Results: $PASS passed, $FAIL failed"
echo "========================================="
[[ $FAIL -eq 0 ]]
