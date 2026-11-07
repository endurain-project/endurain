"""Public operations of the activities' profile transfer."""

import modules.activities.activity_profile_transfer.constants as constants
import modules.activities.activity_profile_transfer.export_service as export_service
import modules.activities.activity_profile_transfer.import_service as import_service
import modules.users.users_profile.contracts as users_profile_contracts


def profile_section() -> users_profile_contracts.ProfileArchiveSection:
    """Return the activities' section of a profile export and import.

    Returns:
        The section, which writes and reads the activities, their components, files and media.
    """
    return users_profile_contracts.ProfileArchiveSection(
        key=constants.PROFILE_ARCHIVE_KEY, export=export_service.export_profile, restore=import_service.restore_profile
    )
