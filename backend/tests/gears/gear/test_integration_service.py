import pytest

import core.exceptions as core_exceptions
import modules.gears.gear.crud as crud
import modules.gears.gear.integration_service as integration
from tests._helpers.gears import gear_create, install_readers


def test_surface_writes_stage_and_leave_the_commit_to_the_caller(db, commit_spy):
    install_readers()
    created = crud.create_gear(gear_create("One"), 1, db)
    integration.create_multiple_gears([gear_create("Two", strava_gear_id="b1")], 1, db)
    integration.delete_all_strava_gear_for_user(1, db)

    commit_spy.assert_not_called()
    assert [g.nickname for g in integration.get_gear_user(1, db)] == ["One"]
    assert integration.get_gear_user_by_id(1, created.id, db) == created


def test_provider_lookups_resolve_the_users_import(db):
    crud.create_gear(gear_create(strava_gear_id="b1", garminconnect_gear_id="g1"), 1, db)

    assert integration.get_gear_by_strava_id("b1", 1, db).nickname == "Road Bike"
    assert integration.get_gear_by_garminconnect_id("g1", 1, db).nickname == "Road Bike"
    assert crud.get_gear_user_by_nickname(1, "road bike", db) is not None


def test_restoring_gears_stages_them_and_publishes_the_ids(db, commit_spy):
    ids: dict[str, dict[int, int]] = {}

    restored = integration.restore_profile_gears([{"id": 5, "nickname": "Garmin", "gear_type": 1}], 1, ids, db)

    commit_spy.assert_not_called()
    assert restored == 1
    assert ids == {"gears": {5: integration.get_gear_user(1, db)[0].id}}


def test_require_owned_gears_refuses_a_foreign_gear(db):
    foreign = crud.create_gear(gear_create(), 2, db)

    with pytest.raises(core_exceptions.NotFoundError):
        integration.require_owned_gears(1, [foreign.id], db)
