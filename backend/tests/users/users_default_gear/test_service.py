"""The default gear service: ownership of the gears, commits and the profile import's remapping."""

import uuid

import pytest

import core.exceptions as core_exceptions
import modules.users.users_default_gear.crud as crud
import modules.users.users_default_gear.schema as schema
import modules.users.users_default_gear.service as service
from tests._factories.gears import make_gear


class TestEditDefaultGear:
    def test_the_users_own_gear_is_assigned(self, db, user):
        gear = make_gear(db, user.id)

        result = service.edit_default_gear(
            schema.UserDefaultGearUpdate(run_gear_id=gear.id), user.id, db, if_match='"1"'
        )

        assert result.run_gear_id == gear.id
        assert crud.get_user_default_gear_by_user_id(user.id, db) == result

    def test_another_users_gear_is_not_found_and_nothing_changes(self, db, user, other):
        foreign = make_gear(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            service.edit_default_gear(schema.UserDefaultGearUpdate(run_gear_id=foreign.id), user.id, db, if_match="*")

        stored = crud.get_user_default_gear_by_user_id(user.id, db)
        assert stored is not None
        assert (stored.run_gear_id, stored.version) == (None, 1)

    def test_a_stale_version_is_a_precondition_failure(self, db, user):
        gear = make_gear(db, user.id)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            service.edit_default_gear(schema.UserDefaultGearUpdate(run_gear_id=gear.id), user.id, db, if_match='"9"')

    def test_missing_settings_are_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            service.edit_default_gear(schema.UserDefaultGearUpdate(), uuid.uuid4(), db, if_match="*")


class TestRestoreProfileDefaultGear:
    def test_archived_gears_are_moved_onto_the_restored_ones(self, db, user):
        archived_run, archived_ride = uuid.uuid4(), uuid.uuid4()
        run, ride = make_gear(db, user.id), make_gear(db, user.id, nickname="Ride")
        record = {
            "id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
            "version": 4,
            "run_gear_id": str(archived_run),
            "ride_gear_id": str(archived_ride),
        }

        restored = service.restore_profile_default_gear(
            record, {"gears": {archived_run: run.id, archived_ride: ride.id}}, user.id, db
        )

        stored = crud.get_user_default_gear_by_user_id(user.id, db)
        assert restored is True
        assert stored is not None
        assert (stored.run_gear_id, stored.ride_gear_id) == (run.id, ride.id)
        assert stored.user_id == user.id

    def test_a_gear_that_was_not_restored_is_dropped(self, db, user):
        record = {"run_gear_id": str(uuid.uuid4()), "ride_gear_id": "not-a-uuid", "walk_gear_id": 5}

        assert service.restore_profile_default_gear(record, {}, user.id, db) is True

        stored = crud.get_user_default_gear_by_user_id(user.id, db)
        assert stored is not None
        assert (stored.run_gear_id, stored.ride_gear_id, stored.walk_gear_id) == (None, None, None)

    def test_the_settings_are_created_when_the_user_has_none(self, db, user):
        db.execute(crud.users_default_gear_models.UsersDefaultGear.__table__.delete())
        assert crud.get_user_default_gear_by_user_id(user.id, db) is None

        assert service.restore_profile_default_gear({}, {}, user.id, db) is True

        assert crud.get_user_default_gear_by_user_id(user.id, db) is not None

    def test_settings_the_schema_refuses_are_skipped(self, db, user):
        assert service.restore_profile_default_gear({"unknown_field": "x"}, {}, user.id, db) is False
