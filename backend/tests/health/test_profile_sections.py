"""The health packages' sections of a profile export and import."""

from unittest.mock import MagicMock, patch

import pytest

import modules.health.health_fasting.integration_service as fasting_integration
import modules.health.health_fasting.service as fasting_service
import modules.health.health_poop.integration_service as poop_integration
import modules.health.health_poop.service as poop_service
import modules.health.health_sleep.integration_service as sleep_integration
import modules.health.health_sleep.service as sleep_service
import modules.health.health_steps.integration_service as steps_integration
import modules.health.health_steps.service as steps_service
import modules.health.health_targets.integration_service as targets_integration
import modules.health.health_targets.service as targets_service
import modules.health.health_water.integration_service as water_integration
import modules.health.health_water.service as water_service
import modules.health.health_weight.integration_service as weight_integration
import modules.health.health_weight.service as weight_service
import modules.users.users_profile.contracts as users_profile_contracts

_SECTIONS = [
    ("health_weight", weight_integration, weight_service),
    ("health_targets", targets_integration, targets_service),
    ("health_sleep", sleep_integration, sleep_service),
    ("health_steps", steps_integration, steps_service),
    ("health_water", water_integration, water_service),
    ("health_fasting", fasting_integration, fasting_service),
    ("health_poop", poop_integration, poop_service),
]


@pytest.mark.parametrize(("key", "integration", "service"), _SECTIONS, ids=[s[0] for s in _SECTIONS])
def test_the_section_is_keyed_by_its_archive_entry_and_restores_through_its_service(key, integration, service):
    section = integration.profile_section()

    assert isinstance(section, users_profile_contracts.ProfileRecordsSection)
    assert section.key == key
    assert section.restore is service.restore_profile_records


@pytest.mark.parametrize(
    ("key", "integration", "crud_name"),
    [
        ("health_weight", weight_integration, "health_weight_crud.get_all_health_weight_by_user_id"),
        ("health_sleep", sleep_integration, "health_sleep_crud.get_health_sleep_by_user_id"),
        ("health_steps", steps_integration, "health_steps_crud.get_health_steps_by_user_id"),
        ("health_water", water_integration, "health_water_crud.get_health_water_by_user_id"),
        ("health_fasting", fasting_integration, "health_fasting_crud.get_health_fasting_by_user_id"),
        ("health_poop", poop_integration, "health_poop_crud.get_health_poop_by_user_id"),
    ],
)
def test_the_section_exports_the_users_records(key, integration, crud_name):
    records = [MagicMock(), MagicMock()]
    db = MagicMock()

    with patch(f"{integration.__name__}.{crud_name}", return_value=records) as read:
        section = integration.profile_section()
        exported = section.export(1, db)

    assert exported == records
    read.assert_called_once_with(1, db)


class TestTargetsSection:
    _READ = "modules.health.health_targets.integration_service.health_targets_crud.get_health_targets_by_user_id"

    def test_exports_the_targets_as_a_one_record_list(self):
        targets = MagicMock()
        with patch(self._READ, return_value=targets):
            assert targets_integration.profile_section().export(1, MagicMock()) == [targets]

    def test_exports_an_empty_list_when_the_user_has_none(self):
        with patch(self._READ, return_value=None):
            assert targets_integration.profile_section().export(1, MagicMock()) == []
