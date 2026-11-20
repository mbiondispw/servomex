@IsTest
private class DemoInboxAddressTest {
    private static final String NORDICGAS_LARS = 'lars.eriksson@nordicgas.no';

    @IsTest
    static void uniqueLocalPartIsKeptAsAlias() {
        Contact lars = contact('Lars', 'Eriksson', NORDICGAS_LARS);
        Contact katrin = contact('Katrin', 'Richter', 'K.Richter@Example.de');
        insertContacts(new List<Contact>{ lars, katrin });

        DemoInboxAddress.RewriteResult result = DemoInboxAddress.rewriteContactEmails();

        Assert.areEqual(2, result.changed);
        Assert.areEqual(0, result.skipped);
        Assert.areEqual(demoInbox('lars.eriksson'), emailOf(lars));
        Assert.areEqual(demoInbox('k.richter'), emailOf(katrin));
    }

    @IsTest
    static void contactsSharingALocalPartFallBackToFirstnameLastname() {
        Contact carole = contact('Carole', 'White', 'info@salesforce.com');
        Contact jon = contact('Jon', 'Amos', 'info@salesforce.com');
        Contact marc = contact('Marc', 'Benioff', 'INFO@example.com');
        insertContacts(new List<Contact>{ carole, jon, marc });

        DemoInboxAddress.rewriteContactEmails();

        Assert.areEqual(demoInbox('carole.white'), emailOf(carole));
        Assert.areEqual(demoInbox('jon.amos'), emailOf(jon));
        Assert.areEqual(demoInbox('marc.benioff'), emailOf(marc));
    }

    @IsTest
    static void blankEmailFallsBackToName() {
        Contact seth = contact('Seth', 'Wilson', null);
        Contact lastNameOnly = contact(null, 'Nakamura', null);
        insertContacts(new List<Contact>{ seth, lastNameOnly });

        DemoInboxAddress.rewriteContactEmails();

        Assert.areEqual(demoInbox('seth.wilson'), emailOf(seth));
        Assert.areEqual(demoInbox('nakamura'), emailOf(lastNameOnly));
    }

    @IsTest
    static void nameWithAccentsOrDisallowedCharactersProducesValidAlias() {
        Contact asa = contact('Åsa', 'Ødegård', null);
        Contact sean = contact('Seán Óg', 'O\'Brien-Smith', null);
        Contact symbols = contact('Zoë!', '(Test) & Co.', null);
        insertContacts(new List<Contact>{ asa, sean, symbols });

        DemoInboxAddress.rewriteContactEmails();

        Assert.areEqual(demoInbox('asa.odegard'), emailOf(asa));
        Assert.areEqual(demoInbox('sean.og.obrien-smith'), emailOf(sean));
        Assert.areEqual(demoInbox('zoe.test.co'), emailOf(symbols));
    }

    @IsTest
    static void aliasStillTakenGetsNumericSuffix() {
        Contact first = contact('Jon', 'Amos', null);
        Contact second = contact('Jon', 'Amos', 'info@salesforce.com');
        Contact third = contact('Jon', 'Amos', 'info@salesforce.com');
        insertContacts(new List<Contact>{ first, second, third });

        DemoInboxAddress.rewriteContactEmails();

        Set<String> emails = new Set<String>{ emailOf(first), emailOf(second), emailOf(third) };
        Assert.areEqual(
            new Set<String>{ demoInbox('jon.amos'), demoInbox('jon.amos2'), demoInbox('jon.amos3') },
            emails
        );
    }

    @IsTest
    static void existingDemoInboxAddressIsUnchangedAndBlocksReuseOfItsAlias() {
        String existingAddress = 'martin.biondi+lars.eriksson@piercewashington.com';
        Contact existing = contact('Lars', 'Demo', existingAddress);
        Contact lars = contact('Lars', 'Eriksson', NORDICGAS_LARS);
        insertContacts(new List<Contact>{ existing, lars });

        DemoInboxAddress.RewriteResult result = DemoInboxAddress.rewriteContactEmails();

        Assert.areEqual(1, result.changed);
        Assert.areEqual(1, result.skipped);
        Assert.areEqual(existingAddress, emailOf(existing));
        Assert.areEqual(demoInbox('lars.eriksson2'), emailOf(lars));
    }

    @IsTest
    static void secondRunChangesNothing() {
        insertContacts(new List<Contact>{
            contact('Lars', 'Eriksson', NORDICGAS_LARS),
            contact('Carole', 'White', 'info@salesforce.com'),
            contact('Jon', 'Amos', 'info@salesforce.com'),
            contact('Seth', 'Wilson', null)
        });
        DemoInboxAddress.rewriteContactEmails();
        Map<Id, String> emailsAfterFirstRun = emailsById();

        DemoInboxAddress.RewriteResult secondRun = DemoInboxAddress.rewriteContactEmails();

        Assert.areEqual(0, secondRun.changed);
        Assert.areEqual(4, secondRun.skipped);
        Assert.areEqual(emailsAfterFirstRun, emailsById());
        Assert.areEqual(4, new Set<String>(emailsAfterFirstRun.values()).size(), 'Every Contact needs its own address.');
        for (String email : emailsAfterFirstRun.values()) {
            Assert.isTrue(DemoInboxAddress.isDemoInboxAddress(email), email);
        }
    }

    @IsTest
    static void checkAcceptsDemoInboxAddresses() {
        for (String address : new List<String>{
            'martin.biondi+lars.eriksson@piercewashington.com',
            'MARTIN.Biondi+a_b-c.1@PierceWashington.COM'
        }) {
            Assert.isTrue(check(address), address);
        }
    }

    @IsTest
    static void checkRefusesEverythingElse() {
        for (String address : new List<String>{
            null,
            '',
            NORDICGAS_LARS,
            'martin.biondi+@piercewashington.com',
            'martin.biondi+Lars@piercewashington.com',
            'martin.biondi+lars eriksson@piercewashington.com',
            'martin.biondi+lars@piercewashington.co.uk',
            'martin.biondi+lars@example.com',
            'martin.biondi+lars@evil.piercewashington.com.example',
            'martin+lars@piercewashington.com',
            'x.martin.biondi+lars@piercewashington.com',
            'martin.biondi@piercewashington.com'
        }) {
            Assert.isFalse(check(address), 'Refused: ' + address);
        }
    }

    private static Boolean check(String address) {
        DemoInboxAddress.CheckRequest request = new DemoInboxAddress.CheckRequest();
        request.emailAddress = address;
        List<DemoInboxAddress.CheckResult> results =
            DemoInboxAddress.check(new List<DemoInboxAddress.CheckRequest>{ request });
        Assert.areEqual(1, results.size());
        return results[0].isDemoInboxAddress;
    }

    private static Contact contact(String firstName, String lastName, String email) {
        return new Contact(FirstName = firstName, LastName = lastName, Email = email);
    }

    private static void insertContacts(List<Contact> contacts) {
        Database.DMLOptions options = new Database.DMLOptions();
        options.OptAllOrNone = true;
        options.DuplicateRuleHeader.allowSave = true;
        Database.insert(contacts, options);
    }

    private static String emailOf(Contact contact) {
        return [SELECT Email FROM Contact WHERE Id = :contact.Id].Email;
    }

    private static Map<Id, String> emailsById() {
        Map<Id, String> emails = new Map<Id, String>();
        for (Contact contact : [SELECT Id, Email FROM Contact]) {
            emails.put(contact.Id, contact.Email);
        }
        return emails;
    }

    private static String demoInbox(String alias) {
        return DemoInboxAddress.PREFIX + alias + DemoInboxAddress.DOMAIN;
    }
}
