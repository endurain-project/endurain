"""Tests for the public surface of the activities' profile transfer."""

import modules.activities.activity_profile_transfer.integration_service as integration_service
import modules.users.users_profile.contracts as users_profile_contracts


def test_profile_section_is_an_archive_section_keyed_activities() -> None:
    section = integration_service.profile_section()

    assert isinstance(section, users_profile_contracts.ProfileArchiveSection)
    assert section.key == "activities"
