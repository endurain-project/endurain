"""The gear integration surface other modules call, on the real database."""

import uuid

import pytest

import core.exceptions as core_exceptions
import modules.gears.gear.crud as crud
import modules.gears.gear.integration_service as integration
import modules.users.users_profile.contracts as users_profile_contracts
from tests._factories.gears import gear_payload, make_gear
from tests._factories.users import make_user


def test_surface_writes_stage_and_leave_the_commit_to_the_caller(committed_sessions):
    with committed_sessions() as db:
        owner = make_user(db)
        db.commit()
    with committed_sessions() as db:
        created = crud.create_gear(gear_payload("One"), owner.id, db)
        integration.create_multiple_gears([gear_payload("Two", strava_gear_id="b1")], owner.id, db)
        integration.delete_all_strava_gear_for_user(owner.id, db)

        assert [g.nickname for g in integration.get_gear_user(owner.id, db)] == ["One"]
        assert integration.get_gear_user_by_id(owner.id, created.id, db) == created
        db.rollback()

    with committed_sessions() as db:
        assert integration.get_gear_user(owner.id, db) == []


def test_provider_lookups_resolve_the_users_import(db, user):
    crud.create_gear(gear_payload(strava_gear_id="b1", garminconnect_gear_id="g1"), user.id, db)

    assert integration.get_gear_by_strava_id("b1", user.id, db).nickname == "Road Bike"
    assert integration.get_gear_by_garminconnect_id("g1", user.id, db).nickname == "Road Bike"
    assert crud.get_gear_user_by_nickname(user.id, "road bike", db) is not None


def test_restoring_gears_stages_them_and_publishes_the_ids(db, user):
    archived_id = uuid.uuid4()
    ids: users_profile_contracts.ProfileIdMaps = {}

    restored = integration.restore_profile_gears(
        [{"id": str(archived_id), "nickname": "Garmin", "gear_type": 1}], user.id, ids, db
    )

    assert restored == 1
    assert ids == {"gears": {archived_id: integration.get_gear_user(user.id, db)[0].id}}


def test_require_owned_gears_refuses_a_foreign_gear(db, user, other):
    foreign = make_gear(db, other.id)

    with pytest.raises(core_exceptions.NotFoundError):
        integration.require_owned_gears(user.id, [foreign.id], db)
