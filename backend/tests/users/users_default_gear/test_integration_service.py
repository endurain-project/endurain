"""What other modules read from and write to the default gear settings."""

import pytest

import core.exceptions as core_exceptions
import modules.users.users_default_gear.integration_service as integration
import modules.users.users_default_gear.schema as schema
import modules.users.users_default_gear.service as service
from tests._factories.gears import make_gear

_RUN = 1
_RIDE = 4
_UNMAPPED = 999


class TestGetDefaultGearForActivityType:
    def test_the_gear_assigned_to_the_type_is_returned(self, db, user):
        gear = make_gear(db, user.id)
        service.stage_default_gear_edit(schema.UserDefaultGearUpdate(run_gear_id=gear.id), user.id, db, if_match="*")

        assert integration.get_default_gear_for_activity_type(user.id, _RUN, db) == gear.id

    def test_an_unassigned_type_has_no_gear(self, db, user):
        assert integration.get_default_gear_for_activity_type(user.id, _RIDE, db) is None

    def test_an_unknown_type_has_no_gear(self, db, user):
        assert integration.get_default_gear_for_activity_type(user.id, _UNMAPPED, db) is None

    def test_a_user_without_settings_has_no_gear(self, db):
        import uuid

        assert integration.get_default_gear_for_activity_type(uuid.uuid4(), _RUN, db) is None


class TestClearDefaultGears:
    def test_the_gear_is_unassigned(self, db, user):
        gear = make_gear(db, user.id)
        service.stage_default_gear_edit(schema.UserDefaultGearUpdate(run_gear_id=gear.id), user.id, db, if_match="*")

        integration.clear_default_gears([gear.id], user.id, db)
        db.expire_all()

        stored = integration.get_default_gear(user.id, db)
        assert stored is not None
        assert stored.run_gear_id is None


def test_creating_the_settings_twice_is_a_conflict(db, user):
    with pytest.raises(core_exceptions.ConflictError):
        integration.create_default_gear(user.id, db)
