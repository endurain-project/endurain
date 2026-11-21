"""The health targets' application rules, on the real database."""

import pytest
import sqlalchemy as sa

import core.exceptions as core_exceptions
import modules.health.health_targets.models as health_targets_models
import modules.health.health_targets.schema as health_targets_schema
import modules.health.health_targets.service as health_targets_service
from tests._factories.users import make_user


@pytest.fixture
def user(db):
    return make_user(db)


def _stored(db, user_id):
    return db.scalar(
        sa.select(health_targets_models.HealthTargets).where(health_targets_models.HealthTargets.user_id == user_id)
    )


class TestUpdate:
    def test_the_change_is_committed_and_read_back(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()

        with committed_sessions() as db:
            updated = health_targets_service.update_health_targets(
                health_targets_schema.HealthTargetsUpdate(weight_kg=75.0), user.id, db, if_match='"1"'
            )

        with committed_sessions() as db:
            assert health_targets_service.get_health_targets(user.id, db) == updated
            assert (updated.weight_kg, updated.version) == (75.0, 2)

    def test_a_stale_version_is_refused_and_nothing_changes(self, db, user):
        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_targets_service.update_health_targets(
                health_targets_schema.HealthTargetsUpdate(weight_kg=75.0), user.id, db, if_match='"5"'
            )

        assert _stored(db, user.id).weight_kg is None

    def test_a_user_without_targets_is_not_found(self, db, user):
        db.execute(
            sa.delete(health_targets_models.HealthTargets).where(health_targets_models.HealthTargets.user_id == user.id)
        )

        with pytest.raises(core_exceptions.NotFoundError):
            health_targets_service.update_health_targets(
                health_targets_schema.HealthTargetsUpdate(weight_kg=75.0), user.id, db, if_match='"1"'
            )


class TestRestoreProfileRecords:
    def test_the_archived_values_edit_the_targets_the_account_has_and_the_row_fields_are_ignored(self, db, user):
        rows = [{"id": "x", "user_id": "y", "version": 4, "weight_kg": 80.0, "steps": 10000}]

        assert health_targets_service.restore_profile_records(rows, user.id, {}, db) == 1

        row = _stored(db, user.id)
        assert (row.weight_kg, row.steps, row.user_id) == (80, 10000, user.id)

    def test_numbers_archived_as_strings_are_read_as_numbers(self, db, user):
        rows = [{"weight_kg": "80.5", "steps": "10000", "sleep_seconds": "28800"}]

        assert health_targets_service.restore_profile_records(rows, user.id, {}, db) == 1

        row = _stored(db, user.id)
        assert (row.weight_kg, row.steps, row.sleep_seconds) == (80.5, 10000, 28800)

    def test_a_number_that_cannot_be_read_is_left_empty_and_the_rest_restored(self, db, user):
        rows = [{"weight_kg": "bad", "steps": "wrong", "sleep_seconds": "nope", "water_ml": 2000.0}]

        assert health_targets_service.restore_profile_records(rows, user.id, {}, db) == 1

        row = _stored(db, user.id)
        assert (row.weight_kg, row.steps, row.sleep_seconds, row.water_ml) == (None, None, None, 2000)

    def test_a_record_the_schema_refuses_is_skipped(self, db, user):
        assert health_targets_service.restore_profile_records([{"steps": -5}, {"steps": 7}], user.id, {}, db) == 1

        assert _stored(db, user.id).steps == 7

    def test_an_archive_without_targets_changes_nothing(self, db, user):
        assert health_targets_service.restore_profile_records([], user.id, {}, db) == 0

        assert _stored(db, user.id).version == 1
