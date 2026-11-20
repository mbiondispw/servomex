// Leaves the demo presenter with only the Servomex Quote Agent in their agent
// panel: removes the presenter's direct RLM_QuotingAgent assignment, so the
// template Revenue Quote Management agent no longer appears for them.
//
// Changes the presenter's assignments only; every other user keeps
// RLM_QuotingAgent. Refuses to run unless the presenter already holds
// SMX_QuotingAgent, so they always keep a quote agent. Re-runnable: when the
// assignment is already gone it changes nothing.
//
// Run it only after the Servomex Quote Agent has passed its agent test (#57).
// Otherwise the presenter is left without a working quote agent on stage.
//
// Run: sf apex run --file scripts/apex/removePresenterTemplateQuotingAgent.apex --target-org <sf-alias>
// Prints PRESENTER_QUOTING_AGENT=removed|unchanged|would-remove <UserId>.
// Set DRY_RUN to true to report the change without writing it. On another org,
// set PRESENTER_USERNAME to that org's presenter.

public class PresenterAccessException extends Exception {}

final Boolean DRY_RUN = false;
final String PRESENTER_USERNAME = 'martin@servomex-demo.00dbm00000pidxheao';
final String KEEP_PERMISSION_SET = 'SMX_QuotingAgent';
final String REMOVE_PERMISSION_SET = 'RLM_QuotingAgent';

List<User> presenters = [SELECT Id, Name FROM User WHERE Username = :PRESENTER_USERNAME AND IsActive = true];
if (presenters.size() != 1) {
    throw new PresenterAccessException('No active user with username ' + PRESENTER_USERNAME + '.');
}
User presenter = presenters[0];

// A permission set held through a permission set group shows up as an
// assignment of the group, not of the permission set.
Set<Id> groupsWithKeep = new Set<Id>();
Set<Id> groupsWithRemove = new Set<Id>();
for (PermissionSetGroupComponent component : [
        SELECT PermissionSetGroupId, PermissionSet.Name
        FROM PermissionSetGroupComponent
        WHERE PermissionSet.Name IN (:KEEP_PERMISSION_SET, :REMOVE_PERMISSION_SET)]) {
    if (component.PermissionSet.Name == KEEP_PERMISSION_SET) {
        groupsWithKeep.add(component.PermissionSetGroupId);
    } else {
        groupsWithRemove.add(component.PermissionSetGroupId);
    }
}

Boolean holdsKeep = false;
List<PermissionSetAssignment> toRemove = new List<PermissionSetAssignment>();
for (PermissionSetAssignment assignment : [
        SELECT Id, PermissionSet.Name, PermissionSetGroupId
        FROM PermissionSetAssignment
        WHERE AssigneeId = :presenter.Id]) {
    if (assignment.PermissionSet.Name == KEEP_PERMISSION_SET || groupsWithKeep.contains(assignment.PermissionSetGroupId)) {
        holdsKeep = true;
    }
    if (assignment.PermissionSet.Name == REMOVE_PERMISSION_SET) {
        toRemove.add(assignment);
    }
    if (groupsWithRemove.contains(assignment.PermissionSetGroupId)) {
        throw new PresenterAccessException(presenter.Name + ' holds ' + REMOVE_PERMISSION_SET
            + ' through permission set group ' + assignment.PermissionSetGroupId
            + '. Removing it would change that group for every member; resolve by hand.');
    }
}

if (!holdsKeep) {
    throw new PresenterAccessException(presenter.Name + ' does not hold ' + KEEP_PERMISSION_SET
        + '. Assign it first, so the presenter keeps a quote agent.');
}

if (toRemove.isEmpty()) {
    System.debug(LoggingLevel.INFO, 'PRESENTER_QUOTING_AGENT=unchanged ' + presenter.Id);
    return;
}

if (DRY_RUN) {
    System.debug(LoggingLevel.INFO, 'PRESENTER_QUOTING_AGENT=would-remove ' + presenter.Id + ' ' + toRemove);
    return;
}

delete toRemove;
System.debug(LoggingLevel.INFO, 'PRESENTER_QUOTING_AGENT=removed ' + presenter.Id + ' (' + toRemove.size()
    + ' ' + REMOVE_PERMISSION_SET + ' assignment)');
