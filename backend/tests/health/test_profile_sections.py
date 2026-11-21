"""The health packages' sections of a profile export and import, on the real database."""

from datetime import UTC, datetime, timedelta

import pytest

import modules.health.health_fasting.integration_service as fasting_integration
import modules.health.health_fasting.schema as fasting_schema
import modules.health.health_fasting.service as fasting_service
import modules.health.health_poop.integration_service as poop_integration
import modules.health.health_sleep.integration_service as sleep_integration
import modules.health.health_steps.integration_service as steps_integration
import modules.health.health_targets.integration_service as targets_integration
import modules.health.health_targets.models as targets_models
import modules.health.health_water.integration_service as water_integration
import modules.health.health_weight.integration_service as weight_integration
import modules.users.users_profile.contracts as users_profile_contracts
from tests._factories import health as health_factories
from tests._factories.users import make_user

_START = datetime(2025, 3, 1, 8, 0, tzinfo=UTC)


def _fast(db, user_id):
    """Stage a completed fast the way an import does, which derives its duration."""
    fasting_service.stage_import_health_fasting(
        user_id,
        fasting_schema.HealthFastingImport(
            fast_start_time=_START, fast_end_time=_START + timedelta(hours=16), status="completed"
        ),
        db,
    )
    return fasting_integration.profile_section().export(user_id, db)[0]


# archive key -> (integration module, stage one record of the kind)
_SECTIONS = {
    "health_weight": (weight_integration, lambda db, uid: health_factories.make_health_weight(db, uid)),
    "health_sleep": (sleep_integration, lambda db, uid: health_factories.make_health_sleep(db, uid)),
    "health_steps": (steps_integration, lambda db, uid: health_factories.make_health_steps(db, uid)),
    "health_water": (water_integration, lambda db, uid: health_factories.make_health_water(db, uid)),
    "health_poop": (poop_integration, lambda db, uid: health_factories.make_health_poop(db, uid)),
    "health_fasting": (fasting_integration, lambda db, uid: _fast(db, uid)),
}
_IDENTITY = {"id", "user_id", "version", "updated_at"}


def _content(records):
    """What a record says, without the identity the database gives it."""
    return [{k: v for k, v in r.model_dump().items() if k not in _IDENTITY} for r in records]


@pytest.fixture
def source(db):
    return make_user(db)


@pytest.fixture
def target(db):
    return make_user(db)


@pytest.mark.parametrize("key", list(_SECTIONS))
class TestRecordSections:
    def test_the_section_is_keyed_by_its_archive_entry(self, key):
        section = _SECTIONS[key][0].profile_section()

        assert isinstance(section, users_profile_contracts.ProfileRecordsSection)
        assert section.key == key

    def test_the_export_lists_the_users_records_only(self, db, source, target, key):
        integration, stage = _SECTIONS[key]
        mine = stage(db, source.id)
        stage(db, target.id)

        exported = integration.profile_section().export(source.id, db)

        assert [record.id for record in exported] == [mine.id]

    def test_a_user_without_records_exports_none(self, db, source, key):
        assert list(_SECTIONS[key][0].profile_section().export(source.id, db)) == []

    def test_an_exported_record_is_restored_for_another_user_with_the_same_content(self, db, source, target, key):
        integration, stage = _SECTIONS[key]
        stage(db, source.id)
        section = integration.profile_section()
        archived = [record.model_dump(mode="json") for record in section.export(source.id, db)]

        restored = section.restore(archived, target.id, {}, db)

        assert restored == 1
        assert _content(section.export(target.id, db)) == _content(section.export(source.id, db))


class TestTargetsSection:
    def test_the_section_is_keyed_by_its_archive_entry(self):
        assert targets_integration.profile_section().key == "health_targets"

    def test_the_targets_are_exported_as_a_one_record_list(self, db, source):
        exported = targets_integration.profile_section().export(source.id, db)

        assert [record.user_id for record in exported] == [source.id]

    def test_archived_targets_edit_the_ones_the_account_started_with(self, db, source, target):
        db.get(targets_models.HealthTargets, targets_integration.get_health_targets(source.id, db).id).steps = 9000
        db.flush()
        section = targets_integration.profile_section()
        archived = [record.model_dump(mode="json") for record in section.export(source.id, db)]

        restored = section.restore(archived, target.id, {}, db)

        assert restored == 1
        assert targets_integration.get_health_targets(target.id, db).steps == 9000
