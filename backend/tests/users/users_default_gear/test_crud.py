"""Default gear settings against the real database: one row per user, edits, and clearing deleted gears."""

import uuid

import pytest
from sqlalchemy import delete, select

import core.exceptions as core_exceptions
import modules.gears.gear.models as gear_models
import modules.users.users.models as users_models
import modules.users.users_default_gear.crud as crud
import modules.users.users_default_gear.models as models
import modules.users.users_default_gear.schema as schema
from modules.users.users_default_gear.constants import ACTIVITY_TYPE_TO_GEAR_ATTR
from tests._factories.gears import make_gear
from tests._factories.users import make_user


class TestReadAndCreate:
    def test_a_new_account_starts_with_empty_settings(self, db, user):
        settings = crud.get_user_default_gear_by_user_id(user.id, db)

        assert settings is not None
        assert settings.user_id == user.id
        assert settings.version == 1
        assert all(getattr(settings, attr) is None for attr in set(ACTIVITY_TYPE_TO_GEAR_ATTR.values()))

    def test_a_user_without_settings_reads_none(self, db):
        assert crud.get_user_default_gear_by_user_id(uuid.uuid4(), db) is None

    def test_a_second_row_for_a_user_is_a_conflict(self, db, user):
        with pytest.raises(core_exceptions.ConflictError):
            crud.create_user_default_gear(user.id, db)


class TestEdit:
    def test_the_set_fields_are_stored_and_the_version_moves(self, db, user):
        gear = make_gear(db, user.id)

        updated = crud.edit_user_default_gear(
            schema.UserDefaultGearUpdate(run_gear_id=gear.id), user.id, db, if_match='"1"'
        )

        assert updated.run_gear_id == gear.id
        assert updated.version == 2
        stored = db.scalars(select(models.UsersDefaultGear).where(models.UsersDefaultGear.user_id == user.id)).one()
        assert stored.run_gear_id == gear.id

    def test_a_field_that_is_not_sent_keeps_its_value(self, db, user):
        run, ride = make_gear(db, user.id), make_gear(db, user.id, nickname="Ride")
        crud.edit_user_default_gear(
            schema.UserDefaultGearUpdate(run_gear_id=run.id, ride_gear_id=ride.id), user.id, db, if_match="*"
        )

        updated = crud.edit_user_default_gear(
            schema.UserDefaultGearUpdate(ride_gear_id=None), user.id, db, if_match="*"
        )

        assert (updated.run_gear_id, updated.ride_gear_id) == (run.id, None)

    def test_a_user_without_settings_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            crud.edit_user_default_gear(schema.UserDefaultGearUpdate(), uuid.uuid4(), db, if_match="*")

    def test_a_stale_version_is_refused(self, db, user):
        with pytest.raises(core_exceptions.PreconditionFailedError):
            crud.edit_user_default_gear(schema.UserDefaultGearUpdate(), user.id, db, if_match='"7"')


class TestClearGears:
    def test_every_column_naming_a_gear_is_nulled_and_the_version_bumped_once(self, db, user):
        gear = make_gear(db, user.id)
        other_gear = make_gear(db, user.id, nickname="Other")
        crud.edit_user_default_gear(
            schema.UserDefaultGearUpdate(run_gear_id=gear.id, trail_run_gear_id=gear.id, ride_gear_id=other_gear.id),
            user.id,
            db,
            if_match="*",
        )
        before = crud.get_user_default_gear_by_user_id(user.id, db)
        assert before is not None

        crud.clear_gears([gear.id], user.id, db)

        db.expire_all()
        after = crud.get_user_default_gear_by_user_id(user.id, db)
        assert after is not None
        assert (after.run_gear_id, after.trail_run_gear_id, after.ride_gear_id) == (None, None, other_gear.id)
        assert after.version == before.version + 1

    def test_gears_no_column_names_change_nothing(self, db, user):
        stranger = make_gear(db, user.id)
        before = crud.get_user_default_gear_by_user_id(user.id, db)

        crud.clear_gears([stranger.id], user.id, db)
        crud.clear_gears([], user.id, db)

        assert crud.get_user_default_gear_by_user_id(user.id, db) == before

    def test_another_users_settings_are_left_alone(self, db, user, other):
        gear = make_gear(db, user.id)
        crud.edit_user_default_gear(schema.UserDefaultGearUpdate(run_gear_id=gear.id), user.id, db, if_match="*")
        before = crud.get_user_default_gear_by_user_id(user.id, db)

        crud.clear_gears([gear.id], other.id, db)

        assert crud.get_user_default_gear_by_user_id(user.id, db) == before


class TestForeignKeys:
    def test_deleting_the_user_deletes_the_settings(self, db):
        doomed = make_user(db)

        db.execute(delete(users_models.Users).where(users_models.Users.id == doomed.id))

        assert crud.get_user_default_gear_by_user_id(doomed.id, db) is None

    def test_deleting_a_gear_unassigns_it_without_touching_the_version(self, db, user):
        gear = make_gear(db, user.id)
        crud.edit_user_default_gear(schema.UserDefaultGearUpdate(run_gear_id=gear.id), user.id, db, if_match="*")
        before = crud.get_user_default_gear_by_user_id(user.id, db)
        assert before is not None

        db.execute(delete(gear_models.Gear).where(gear_models.Gear.id == gear.id))
        db.expire_all()

        after = crud.get_user_default_gear_by_user_id(user.id, db)
        assert after is not None
        assert after.run_gear_id is None
        assert after.version == before.version
