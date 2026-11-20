// Service Upsell test cleanup (#56): deletes what Servomex Quote Agent test
// runs leave on Service Upsell Test Customer, so repeated runs don't pile up
// records. It deletes every quote on the account's opportunities and every
// opportunity except the fixture opportunity, which it keeps for the next run.
//
//   sf apex run -o <sf-alias> -f scripts/apex/smxServiceUpsellCleanup.apex
String accountName = 'Service Upsell Test Customer';
String fixtureOpportunityName = 'Service Upsell Existing Opportunity';

List<Account> accounts = [SELECT Id FROM Account WHERE Name = :accountName];
if (accounts.size() != 1) {
    throw new IllegalArgumentException('Expected one Account named ' + accountName + ', found ' + accounts.size() + '; run smxServiceUpsellFixture.apex first.');
}
Id accountId = accounts[0].Id;

List<Opportunity> opps = [SELECT Id, Name, SyncedQuoteId FROM Opportunity WHERE AccountId = :accountId];
List<Opportunity> toUnsync = new List<Opportunity>();
List<Opportunity> toDelete = new List<Opportunity>();
for (Opportunity opp : opps) {
    if (opp.Name == fixtureOpportunityName) {
        if (opp.SyncedQuoteId != null) {
            toUnsync.add(new Opportunity(Id = opp.Id, SyncedQuoteId = null));
        }
    } else {
        toDelete.add(opp);
    }
}
List<Quote> quotes = [SELECT Id FROM Quote WHERE OpportunityId IN :opps];

update toUnsync;
delete quotes;
delete toDelete;
System.debug(LoggingLevel.INFO, 'Service Upsell cleanup: deleted ' + quotes.size() + ' quotes and ' + toDelete.size() + ' opportunities; kept ' + fixtureOpportunityName + '.');
