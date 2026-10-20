from unittest.mock import MagicMock

import pytest

import core.exceptions as core_exceptions
import modules.gears.gear.crud as crud
import modules.gears.gear.integration_service as integration
import modules.gears.gear.schema as schema


def _gear(nickname="Road Bike", **overrides) -> schema.GearCreate:
    return schema.GearCreate(**{"nickname": nickname, "gear_type": schema.GearType.BIKE, **overrides})


def test_surface_writes_stage_and_leave_the_commit_to_the_caller(db):
    spy = MagicMock(wraps=db.commit)
    db.commit = spy

    created = integration.create_gear(_gear("One"), 1, db)
    integration.create_multiple_gears([_gear("Two", strava_gear_id="b1")], 1, db)
    integration.delete_all_strava_gear_for_user(1, db)

    spy.assert_not_called()
    assert [g.nickname for g in integration.get_gear_user(1, db)] == ["One"]
    assert integration.get_gear_user_by_id(1, created.id, db) == created


def test_provider_lookups_resolve_the_users_import(db):
    crud.create_gear(_gear(strava_gear_id="b1", garminconnect_gear_id="g1"), 1, db)

    assert integration.get_gear_by_strava_id("b1", 1, db).nickname == "Road Bike"
    assert integration.get_gear_by_garminconnect_id("g1", 1, db).nickname == "Road Bike"
    assert integration.get_gear_user_by_nickname(1, "road bike", db) is not None


def test_a_repeated_nickname_is_a_conflict(db):
    integration.create_gear(_gear(), 1, db)

    with pytest.raises(core_exceptions.ConflictError):
        integration.create_gear(_gear(), 1, db)


def test_require_owned_gears_refuses_a_foreign_gear(db):
    foreign = crud.create_gear(_gear(), 2, db)

    with pytest.raises(core_exceptions.NotFoundError):
        integration.require_owned_gears(1, [foreign.id], db)
