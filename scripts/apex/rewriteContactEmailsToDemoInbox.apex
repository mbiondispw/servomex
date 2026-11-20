// Gives every Contact in the org a unique Demo Inbox Address
// (martin.biondi+<alias>@piercewashington.com). Re-runnable: Contacts that
// already hold one are skipped. Requires DemoInboxAddress (deploy_servomex).
DemoInboxAddress.RewriteResult result = DemoInboxAddress.rewriteContactEmails();
System.debug(LoggingLevel.INFO, 'Demo Inbox Address rewrite: ' + result.changed + ' Contacts changed, ' + result.skipped + ' skipped (already a Demo Inbox Address).');
