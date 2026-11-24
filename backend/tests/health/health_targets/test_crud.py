"""The health targets' persistence, on the real database."""

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.health.health_targets.crud as health_targets_crud
import modules.health.health_targets.models as health_targets_models
import modules.health.health_targets.schema as health_targets_schema
from tests._factories.users import make_user


@pytest.fixture
def user(db):
    return make_user(db)


@pytest.fixture
def other(db):
    return make_user(db)


def _stored(db, user_id):
    return db.scalar(
        sa.select(health_targets_models.HealthTargets).where(health_targets_models.HealthTargets.user_id == user_id)
    )


class TestRead:
    def test_a_new_account_starts_with_empty_targets(self, db, user):
        targets = health_targets_crud.get_health_targets_by_user_id(user.id, db)

        assert targets is not None
        assert (targets.user_id, targets.version) == (user.id, 1)
        assert {
            targets.weight_kg,
            targets.steps,
            targets.sleep_seconds,
            targets.fasting_seconds,
            targets.water_ml,
            targets.poop_count,
        } == {None}

    def test_a_user_without_targets_has_none(self, db, user):
        db.execute(
            sa.delete(health_targets_models.HealthTargets).where(health_targets_models.HealthTargets.user_id == user.id)
        )

        assert health_targets_crud.get_health_targets_by_user_id(user.id, db) is None
        assert health_targets_crud.health_targets_exists(user.id, db) is False

    def test_targets_exist_for_a_user_who_has_them(self, db, user, other):
        assert health_targets_crud.health_targets_exists(user.id, db) is True

    def test_another_users_targets_are_not_read(self, db, user, other):
        health_targets_crud.edit_health_targets(
            health_targets_schema.HealthTargetsUpdate(steps=9000), other.id, db, if_match='"1"'
        )

        assert health_targets_crud.get_health_targets_by_user_id(user.id, db).steps is None


class TestCreate:
    def test_a_second_set_of_targets_is_a_conflict(self, db, user):
        with pytest.raises(core_exceptions.ConflictError, match="Duplicate entry"):
            health_targets_crud.create_health_targets(user.id, db)

    def test_the_database_holds_one_set_per_user(self, db, user):
        with pytest.raises(IntegrityError, match="health_targets_user_id"):
            db.add(health_targets_models.HealthTargets(user_id=user.id))
            db.flush()

    def test_deleting_the_user_deletes_their_targets(self, db, user):
        db.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": user.id})

        assert _stored(db, user.id) is None


class TestEdit:
    def test_the_given_fields_are_stored_and_the_version_moves_on(self, db, user):
        edited = health_targets_crud.edit_health_targets(
            health_targets_schema.HealthTargetsUpdate(weight_kg=72.5, steps=10000, sleep_seconds=28800),
            user.id,
            db,
            if_match='"1"',
        )

        row = _stored(db, user.id)
        assert (row.weight_kg, row.steps, row.sleep_seconds, row.version) == (72.5, 10000, 28800, 2)
        assert (edited.weight_kg, edited.version) == (72.5, 2)

    def test_a_field_not_given_keeps_its_value(self, db, user):
        health_targets_crud.edit_health_targets(
            health_targets_schema.HealthTargetsUpdate(steps=10000, water_ml=2500.0), user.id, db, if_match='"1"'
        )

        health_targets_crud.edit_health_targets(
            health_targets_schema.HealthTargetsUpdate(steps=12000), user.id, db, if_match='"2"'
        )

        row = _stored(db, user.id)
        assert (row.steps, row.water_ml) == (12000, 2500)

    def test_a_field_given_as_null_is_cleared(self, db, user):
        health_targets_crud.edit_health_targets(
            health_targets_schema.HealthTargetsUpdate(steps=10000, poop_count=2), user.id, db, if_match='"1"'
        )

        health_targets_crud.edit_health_targets(
            health_targets_schema.HealthTargetsUpdate(steps=None), user.id, db, if_match='"2"'
        )

        row = _stored(db, user.id)
        assert (row.steps, row.poop_count) == (None, 2)

    def test_a_user_without_targets_has_nothing_to_edit(self, db, user):
        db.execute(
            sa.delete(health_targets_models.HealthTargets).where(health_targets_models.HealthTargets.user_id == user.id)
        )

        with pytest.raises(core_exceptions.NotFoundError, match="Health targets not found"):
            health_targets_crud.edit_health_targets(
                health_targets_schema.HealthTargetsUpdate(steps=1), user.id, db, if_match='"1"'
            )

    def test_a_stale_version_is_refused_and_the_targets_keep_their_values(self, db, user):
        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_targets_crud.edit_health_targets(
                health_targets_schema.HealthTargetsUpdate(steps=1), user.id, db, if_match='"7"'
            )

        assert (_stored(db, user.id).steps, _stored(db, user.id).version) == (None, 1)
