"""Deleting a gear unassigns it from the default gear settings and invalidates their ETag."""

import pytest

import core.exceptions as core_exceptions
import modules.gears.gear.crud as gear_crud
import modules.gears.gear.service as gear_service
import modules.users.users_default_gear.integration_service as integration
import modules.users.users_default_gear.schema as schema
import modules.users.users_default_gear.service as service
from tests._factories.gears import gear_payload, make_gear


def _settings(db, user):
    db.expire_all()
    stored = integration.get_default_gear(user.id, db)
    assert stored is not None
    return stored


@pytest.fixture
def assigned(db, user):
    """A run gear and a ride gear, both set as defaults."""
    run = gear_crud.create_gear(gear_payload("Run", strava_gear_id="s1"), user.id, db)
    ride = make_gear(db, user.id, nickname="Ride")
    service.stage_default_gear_edit(
        schema.UserDefaultGearUpdate(run_gear_id=run.id, ride_gear_id=ride.id), user.id, db, if_match="*"
    )
    return run, ride


def test_deleting_the_default_gear_bumps_the_version_and_refuses_the_old_tag(db, user, assigned):
    run, ride = assigned
    before = _settings(db, user)

    gear_service.delete_gear(run.id, user.id, db, if_match="*")

    after = _settings(db, user)
    assert after.version == before.version + 1
    assert (after.run_gear_id, after.ride_gear_id) == (None, ride.id)
    with pytest.raises(core_exceptions.PreconditionFailedError):
        service.edit_default_gear(
            schema.UserDefaultGearUpdate(walk_gear_id=None), user.id, db, if_match=f'"{before.version}"'
        )


def test_deleting_an_unrelated_gear_keeps_the_version(db, user, assigned):
    unrelated = make_gear(db, user.id, nickname="Other")
    before = _settings(db, user)

    gear_service.delete_gear(unrelated.id, user.id, db, if_match="*")

    assert _settings(db, user).version == before.version


def test_unlinking_strava_bumps_the_version_once_for_all_its_gears(db, user, assigned):
    _, ride = assigned
    before = _settings(db, user)

    gear_service.delete_all_strava_gear_for_user(user.id, db)

    after = _settings(db, user)
    assert after.version == before.version + 1
    assert (after.run_gear_id, after.ride_gear_id) == (None, ride.id)
