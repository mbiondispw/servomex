// One-time product bootstrap for the SERVOFLEX Mini MP Portable Analyser.
//
// Gives the org's existing Mini MP product (legacy ProductCode SFX-5200-MP) its
// SAP material identity, so every data plan can match it on StockKeepingUnit.
// Updates the record in place, so existing references keep working, and never
// creates a Product. Repeatable: once bootstrapped, the product is found by its
// new identity and re-running changes nothing.
//
// Run: sf apex run --file scripts/apex/bootstrapMiniMpProduct.apex --target-org <sf-alias>

public class BootstrapException extends Exception {}

final String LEGACY_PRODUCT_CODE = 'SFX-5200-MP';
final String SAP_MATERIAL = '05230A1';
final String PRODUCT_NAME = 'SERVOFLEX Mini MP Portable Analyser';

List<Product2> matches = [
    SELECT Id, Name, ProductCode, StockKeepingUnit
    FROM Product2
    WHERE ProductCode = :LEGACY_PRODUCT_CODE
       OR ProductCode = :SAP_MATERIAL
       OR StockKeepingUnit = :SAP_MATERIAL
];
if (matches.size() != 1) {
    throw new BootstrapException('Expected exactly one Mini MP product (ProductCode '
        + LEGACY_PRODUCT_CODE + ' or ' + SAP_MATERIAL + ', or SKU ' + SAP_MATERIAL
        + '), found ' + matches.size() + '. Resolve by hand; this script never creates or merges Products.');
}

Product2 product = matches[0];
if (product.StockKeepingUnit == SAP_MATERIAL
        && product.ProductCode == SAP_MATERIAL
        && product.Name == PRODUCT_NAME) {
    System.debug('MINIMP_BOOTSTRAP=unchanged ' + product.Id);
} else {
    product.StockKeepingUnit = SAP_MATERIAL;
    product.ProductCode = SAP_MATERIAL;
    product.Name = PRODUCT_NAME;
    update matches;
    System.debug('MINIMP_BOOTSTRAP=updated ' + product.Id);
}
