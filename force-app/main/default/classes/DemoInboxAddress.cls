/**
 * The Demo Inbox Address rule: martin.biondi+<alias>@piercewashington.com is the
 * only kind of address a Contact in a demo org may hold, so no Proposal reaches a
 * real customer. Send Proposal checks it; the contact email rewrite enforces it.
 */
public inherited sharing class DemoInboxAddress {
    @TestVisible
    private static final String PREFIX = 'martin.biondi+';
    @TestVisible
    private static final String DOMAIN = '@piercewashington.com';

    // Contact.Email holds 80 characters; this leaves room for the prefix, domain and a suffix.
    private static final Integer MAX_ALIAS_BASE_LENGTH = 40;

    private static final Pattern VALID_ALIAS = Pattern.compile('[a-z0-9._-]+');

    private static final Map<String, String> ACCENT_REPLACEMENTS = new Map<String, String>{
        'à' => 'a', 'á' => 'a', 'â' => 'a', 'ã' => 'a', 'ä' => 'a', 'å' => 'a', 'ā' => 'a', 'ą' => 'a', 'ă' => 'a',
        'æ' => 'ae', 'ç' => 'c', 'ć' => 'c', 'č' => 'c', 'ď' => 'd', 'đ' => 'd', 'ð' => 'd',
        'è' => 'e', 'é' => 'e', 'ê' => 'e', 'ë' => 'e', 'ē' => 'e', 'ę' => 'e', 'ě' => 'e',
        'ğ' => 'g', 'ì' => 'i', 'í' => 'i', 'î' => 'i', 'ï' => 'i', 'ī' => 'i', 'ı' => 'i',
        'ł' => 'l', 'ñ' => 'n', 'ń' => 'n', 'ň' => 'n',
        'ò' => 'o', 'ó' => 'o', 'ô' => 'o', 'õ' => 'o', 'ö' => 'o', 'ø' => 'o', 'ō' => 'o', 'ő' => 'o',
        'œ' => 'oe', 'ř' => 'r', 'ś' => 's', 'š' => 's', 'ş' => 's', 'ß' => 'ss', 'ť' => 't', 'þ' => 'th',
        'ù' => 'u', 'ú' => 'u', 'û' => 'u', 'ü' => 'u', 'ū' => 'u', 'ů' => 'u', 'ű' => 'u',
        'ý' => 'y', 'ÿ' => 'y', 'ź' => 'z', 'ż' => 'z', 'ž' => 'z'
    };

    public class CheckRequest {
        @InvocableVariable(
            label='Email Address'
            description='The email address to check, for example the Quote Contact\'s Email.'
        )
        public String emailAddress;
    }

    public class CheckResult {
        @InvocableVariable(
            label='Is Demo Inbox Address'
            description='True when the address has the form martin.biondi+<alias>@piercewashington.com.'
        )
        public Boolean isDemoInboxAddress;
    }

    public class RewriteResult {
        public Integer changed = 0;
        public Integer skipped = 0;
    }

    @InvocableMethod(
        label='Check Demo Inbox Address'
        description='Says whether an email address is a Demo Inbox Address (martin.biondi+<alias>@piercewashington.com). A blank address is not.'
        category='Quote Delivery'
    )
    public static List<CheckResult> check(List<CheckRequest> requests) {
        List<CheckResult> results = new List<CheckResult>();
        for (CheckRequest request : requests) {
            CheckResult result = new CheckResult();
            result.isDemoInboxAddress = isDemoInboxAddress(request?.emailAddress);
            results.add(result);
        }
        return results;
    }

    /**
     * The prefix and domain match case-insensitively; the alias must be non-empty
     * and hold only lowercase letters, digits, '.', '_' and '-'.
     */
    public static Boolean isDemoInboxAddress(String address) {
        return aliasOf(address) != null;
    }

    /**
     * Gives every Contact in the org a unique Demo Inbox Address. Contacts that already
     * hold one are skipped and keep their alias. Safe to re-run.
     */
    public static RewriteResult rewriteContactEmails() {
        RewriteResult result = new RewriteResult();
        Set<String> takenAliases = new Set<String>();
        List<Contact> toRewrite = new List<Contact>();
        Map<String, Integer> contactsByLocalPart = new Map<String, Integer>();

        for (Contact contact : [SELECT Id, FirstName, LastName, Email FROM Contact ORDER BY CreatedDate, Id]) {
            String existingAlias = aliasOf(contact.Email);
            if (existingAlias != null) {
                takenAliases.add(existingAlias);
                result.skipped++;
                continue;
            }
            toRewrite.add(contact);
            String localPart = localPartOf(contact.Email);
            if (localPart != null) {
                Integer count = contactsByLocalPart.get(localPart);
                contactsByLocalPart.put(localPart, count == null ? 1 : count + 1);
            }
        }

        // Email-derived aliases are claimed before name-derived ones, so a Contact keeps
        // its own local part even when another Contact's name would produce the same alias.
        Map<Id, String> aliasByContactId = new Map<Id, String>();
        List<Contact> needNameAlias = new List<Contact>();
        for (Contact contact : toRewrite) {
            String localPart = localPartOf(contact.Email);
            String alias = (localPart == null || contactsByLocalPart.get(localPart) > 1) ? null : toAlias(localPart);
            if (String.isBlank(alias)) {
                needNameAlias.add(contact);
            } else {
                aliasByContactId.put(contact.Id, claim(alias, takenAliases));
            }
        }
        for (Contact contact : needNameAlias) {
            aliasByContactId.put(contact.Id, claim(nameAliasOf(contact), takenAliases));
        }

        List<Contact> updates = new List<Contact>();
        for (Contact contact : toRewrite) {
            updates.add(new Contact(Id = contact.Id, Email = PREFIX + aliasByContactId.get(contact.Id) + DOMAIN));
        }
        if (!updates.isEmpty()) {
            Database.DMLOptions options = new Database.DMLOptions();
            options.OptAllOrNone = true;
            options.DuplicateRuleHeader.allowSave = true;
            Database.update(updates, options);
        }
        result.changed = updates.size();
        return result;
    }

    private static String aliasOf(String address) {
        if (String.isBlank(address)) {
            return null;
        }
        String lower = address.toLowerCase();
        if (lower.length() != address.length() || !lower.startsWith(PREFIX) || !lower.endsWith(DOMAIN)) {
            return null;
        }
        String alias = address.substring(PREFIX.length(), address.length() - DOMAIN.length());
        return VALID_ALIAS.matcher(alias).matches() ? alias : null;
    }

    private static String localPartOf(String address) {
        if (String.isBlank(address) || !address.contains('@')) {
            return null;
        }
        String localPart = address.substringBeforeLast('@').trim().toLowerCase();
        return String.isBlank(localPart) ? null : localPart;
    }

    private static String nameAliasOf(Contact contact) {
        String name = String.isBlank(contact.FirstName) ? contact.LastName : contact.FirstName + ' ' + contact.LastName;
        String alias = toAlias(name);
        return String.isBlank(alias) ? 'contact' : alias;
    }

    private static String toAlias(String text) {
        if (text == null) {
            return null;
        }
        String lower = text.trim().toLowerCase();
        String stripped = '';
        for (Integer i = 0; i < lower.length(); i++) {
            String character = lower.substring(i, i + 1);
            String replacement = ACCENT_REPLACEMENTS.get(character);
            stripped += replacement == null ? character : replacement;
        }
        String alias = stripped
            .replaceAll('\\s+', '.')
            .replaceAll('[^a-z0-9._-]', '')
            .replaceAll('\\.{2,}', '.');
        alias = alias.left(MAX_ALIAS_BASE_LENGTH).removeStart('.').removeEnd('.');
        return alias;
    }

    private static String claim(String alias, Set<String> takenAliases) {
        String candidate = alias;
        Integer suffix = 2;
        while (takenAliases.contains(candidate)) {
            candidate = alias + suffix;
            suffix++;
        }
        takenAliases.add(candidate);
        return candidate;
    }
}
