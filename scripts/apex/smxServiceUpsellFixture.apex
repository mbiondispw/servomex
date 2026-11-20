// Service Upsell test fixture (#56): a GBP test account, Service Upsell Test
// Customer, with one open fixture opportunity for the Servomex Quote Agent test.
// Re-runnable: reuses both records when they exist and never creates a second
// one. Pair with smxServiceUpsellCleanup.apex after each agent test run.
//
//   sf apex run -o <sf-alias> -f scripts/apex/smxServiceUpsellFixture.apex
String accountName = 'Service Upsell Test Customer';
String opportunityName = 'Service Upsell Existing Opportunity';

List<Account> accounts = [SELECT Id, CurrencyIsoCode FROM Account WHERE Name = :accountName];
if (accounts.size() > 1) {
    throw new IllegalArgumentException('More than one Account named ' + accountName + '; delete the extras first.');
}
Account acct;
if (accounts.isEmpty()) {
    acct = new Account(Name = accountName, Type = 'Customer');
    acct.put('CurrencyIsoCode', 'GBP');
    insert acct;
} else {
    acct = accounts[0];
    if (acct.get('CurrencyIsoCode') != 'GBP') {
        throw new IllegalArgumentException(accountName + ' is ' + acct.get('CurrencyIsoCode') + ', not GBP; fix it by hand.');
    }
}

Pricebook2 standardBook = [SELECT Id FROM Pricebook2 WHERE IsStandard = true LIMIT 1];
List<Opportunity> opps = [SELECT Id, IsClosed FROM Opportunity WHERE AccountId = :acct.Id AND Name = :opportunityName];
if (opps.size() > 1) {
    throw new IllegalArgumentException('More than one fixture opportunity on ' + accountName + '; delete the extras first.');
}
Opportunity opp;
if (opps.isEmpty()) {
    // Created directly at Proposal/Quote: Require_Next_Step_After_Qualification
    // fires only on stage changes, and Next Step is set for later changes.
    opp = new Opportunity(
        Name = opportunityName,
        AccountId = acct.Id,
        StageName = 'Proposal/Quote',
        CloseDate = Date.today().addDays(30),
        NextStep = 'Send services quote',
        Pricebook2Id = standardBook.Id
    );
    opp.put('CurrencyIsoCode', 'GBP');
    insert opp;
} else {
    opp = opps[0];
    if (opp.IsClosed) {
        throw new IllegalArgumentException('The fixture opportunity is closed; reopen it by hand.');
    }
}
System.debug(LoggingLevel.INFO, 'Service Upsell fixture ready: Account ' + acct.Id + ', Opportunity ' + opp.Id + ' (' + opportunityName + ')');
