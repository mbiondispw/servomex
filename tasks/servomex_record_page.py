"""Assign a record page per profile in a Lightning app.

rlm-base-dev's UX assembly owns RLM_Quote_Record_Page and its org-default and
app-default assignments. App + profile assignments are the one layer it doesn't
write, so Servomex_Quote_Record_Page (which adds Send Proposal) is assigned there.
"""

from cumulusci.core.utils import process_list_arg
from cumulusci.tasks.metadata_etl import MetadataSingleEntityTransformTask
from cumulusci.utils.xml.metadata_tree import MetadataElement


class AssignRecordPageToProfiles(MetadataSingleEntityTransformTask):
    entity = "CustomApplication"
    task_options = {
        "flexipage": {"description": "FlexiPage to assign.", "required": True},
        "sobject": {"description": "Object whose record page is assigned.", "required": True},
        "profiles": {
            "description": "Profile API names (e.g. Admin for System Administrator).",
            "required": True,
        },
        **MetadataSingleEntityTransformTask.task_options,
    }

    def _init_options(self, kwargs):
        super()._init_options(kwargs)
        self.profiles = process_list_arg(self.options["profiles"])

    def _transform_entity(self, metadata: MetadataElement, api_name: str):
        flexipage = self.options["flexipage"]
        sobject = self.options["sobject"]
        for profile in self.profiles:
            override = metadata.find(
                "profileActionOverrides",
                actionName="View",
                pageOrSobjectType=sobject,
                formFactor="Large",
                profile=profile,
                recordType=None,
            )
            if override is not None:
                override.content.text = flexipage
                self.logger.info(f"{api_name}: {profile} {sobject} page set to {flexipage}")
                continue

            anchor = next(
                (
                    e
                    for e in (metadata.find(t) for t in ("setupExperience", "tabs", "uiType"))
                    if e is not None
                ),
                None,
            )
            override = (
                metadata.insert_before(anchor, "profileActionOverrides")
                if anchor is not None
                else metadata.append("profileActionOverrides")
            )
            override.append("actionName", "View")
            override.append("content", flexipage)
            override.append("formFactor", "Large")
            override.append("pageOrSobjectType", sobject)
            override.append("type", "Flexipage")
            override.append("profile", profile)
            self.logger.info(f"{api_name}: {profile} {sobject} page assigned to {flexipage}")
        return metadata
