// Service Upsell test fixture (#56): a GBP test account, Service Upsell Test
// Customer, with one open and one Closed Lost fixture opportunity for the
// Servomex Quote Agent tests (#56, #57).
// Re-runnable: reuses the records when they exist and never creates a second
// one. Pair with smxServiceUpsellCleanup.apex after each agent test run.
//
//   sf apex run -o <sf-alias> -f scripts/apex/smxServiceUpsellFixture.apex
String accountName = 'Service Upsell Test Customer';
String opportunityName = 'Service Upsell Existing Opportunity';
String closedOpportunityName = 'Service Upsell Closed Opportunity';

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
List<Opportunity> closedOpps = [SELECT Id, StageName FROM Opportunity WHERE AccountId = :acct.Id AND Name = :closedOpportunityName];
if (closedOpps.size() > 1) {
    throw new IllegalArgumentException('More than one closed fixture opportunity on ' + accountName + '; delete the extras first.');
}
Opportunity closedOpp;
if (closedOpps.isEmpty()) {
    closedOpp = new Opportunity(
        Name = closedOpportunityName,
        AccountId = acct.Id,
        StageName = 'Closed Lost',
        CloseDate = Date.today(),
        Pricebook2Id = standardBook.Id
    );
    closedOpp.put('CurrencyIsoCode', 'GBP');
    insert closedOpp;
} else {
    closedOpp = closedOpps[0];
    if (closedOpp.StageName != 'Closed Lost') {
        throw new IllegalArgumentException('The closed fixture opportunity is ' + closedOpp.StageName + ', not Closed Lost; fix it by hand.');
    }
}
System.debug(LoggingLevel.INFO, 'Service Upsell fixture ready: Account ' + acct.Id + ', Opportunity ' + opp.Id + ' (' + opportunityName + '), Opportunity ' + closedOpp.Id + ' (' + closedOpportunityName + ')');
