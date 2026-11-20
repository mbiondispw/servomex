// Sets the Act 10 demo customer, Lonza Biologics UK Ltd, to account currency
// GBP, so a new Service Upsell opportunity for it quotes in GBP by default.
//
// Re-runnable: when Lonza is already GBP it changes nothing. Fails, and writes
// nothing, unless exactly one account has that name. Lonza's existing
// opportunities keep their own currency: the script checks them after the
// update and rolls back if any of them changed.
//
// Run: sf apex run --file scripts/apex/setLonzaAccountCurrencyToGbp.apex --target-org <sf-alias>
// Prints LONZA_CURRENCY=updated|unchanged|would-update <AccountId>.
// Set DRY_RUN to true to report the change without writing it.

public class LonzaCurrencyException extends Exception {}

final Boolean DRY_RUN = false;
final String ACCOUNT_NAME = 'Lonza Biologics UK Ltd';
final String TARGET_CURRENCY = 'GBP';

List<Account> matches = [SELECT Id, CurrencyIsoCode FROM Account WHERE Name = :ACCOUNT_NAME];
if (matches.size() != 1) {
    throw new LonzaCurrencyException('Expected exactly one Account named "' + ACCOUNT_NAME
        + '", found ' + matches.size() + '. This script never creates or merges Accounts.');
}
Account lonza = matches[0];

if (lonza.CurrencyIsoCode == TARGET_CURRENCY) {
    System.debug(LoggingLevel.INFO, 'LONZA_CURRENCY=unchanged ' + lonza.Id);
    return;
}

Map<Id, String> currencyBefore = new Map<Id, String>();
for (Opportunity opp : [SELECT Id, CurrencyIsoCode FROM Opportunity WHERE AccountId = :lonza.Id]) {
    currencyBefore.put(opp.Id, opp.CurrencyIsoCode);
}

if (DRY_RUN) {
    System.debug(LoggingLevel.INFO, 'LONZA_CURRENCY=would-update ' + lonza.Id + ' ' + lonza.CurrencyIsoCode
        + ' -> ' + TARGET_CURRENCY + '; ' + currencyBefore.size() + ' opportunities keep ' + currencyBefore.values());
    return;
}

lonza.CurrencyIsoCode = TARGET_CURRENCY;
update lonza;

for (Opportunity opp : [SELECT Id, CurrencyIsoCode FROM Opportunity WHERE Id IN :currencyBefore.keySet()]) {
    if (opp.CurrencyIsoCode != currencyBefore.get(opp.Id)) {
        throw new LonzaCurrencyException('Opportunity ' + opp.Id + ' changed currency from '
            + currencyBefore.get(opp.Id) + ' to ' + opp.CurrencyIsoCode + '; the account update was rolled back.');
    }
}
System.debug(LoggingLevel.INFO, 'LONZA_CURRENCY=updated ' + lonza.Id + ' -> ' + TARGET_CURRENCY
    + '; ' + currencyBefore.size() + ' opportunities kept their currency');
