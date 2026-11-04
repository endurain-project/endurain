"""Deleting a gear invalidates the default-gear ETag against real PostgreSQL."""

import pytest
from sqlalchemy import select

import core.exceptions as core_exceptions
import modules.gears.gear.service as gear_service
import modules.users.users_default_gear.integration_service as default_gear_integration
import modules.users.users_default_gear.models as default_gear_models
import modules.users.users_default_gear.schema as default_gear_schema
import modules.users.users_default_gear.service as default_gear_service
from module_registry import configure_gear_contributors
from tests._helpers.db import ensure_user
from tests._helpers.gears import gear_create


@pytest.fixture
def factory(pg_factory):
    ensure_user(pg_factory, 1)
    configure_gear_contributors()
    return pg_factory


def _default_gear_row(factory):
    with factory() as db:
        return db.scalars(select(default_gear_models.UsersDefaultGear)).one()


def _setup(factory, *, strava: bool = False):
    """Create the user's settings with run and ride defaults on two gears."""
    with factory() as db:
        run = gear_service.create_gear(gear_create("Run", strava_gear_id="s1" if strava else None), 1, db)
        ride = gear_service.create_gear(gear_create("Ride"), 1, db)
        default_gear_integration.create_default_gear(1, db)
        db.commit()
        default_gear_integration.edit_default_gear(
            default_gear_schema.UsersDefaultGearUpdate(run_gear_id=run.id, ride_gear_id=ride.id),
            1,
            db,
            if_match="*",
        )
        db.commit()
    return run.id, ride.id


def test_deleting_the_default_gear_bumps_the_version_and_refuses_the_old_tag(factory):
    run_id, ride_id = _setup(factory)
    before = _default_gear_row(factory)

    with factory() as db:
        gear_service.delete_gear(run_id, 1, db, if_match="*")

    after = _default_gear_row(factory)
    assert after.version == before.version + 1
    assert after.run_gear_id is None
    assert after.ride_gear_id == ride_id
    with factory() as db, pytest.raises(core_exceptions.PreconditionFailedError):
        default_gear_service.edit_default_gear(
            default_gear_schema.UsersDefaultGearUpdate(walk_gear_id=None), 1, db, if_match=f'"{before.version}"'
        )


def test_deleting_an_unrelated_gear_keeps_the_version(factory):
    _setup(factory)
    with factory() as db:
        other = gear_service.create_gear(gear_create("Other"), 1, db)
    before = _default_gear_row(factory)

    with factory() as db:
        gear_service.delete_gear(other.id, 1, db, if_match="*")

    assert _default_gear_row(factory).version == before.version


def test_unlinking_strava_bumps_the_version_once_for_all_its_gears(factory):
    _, ride_id = _setup(factory, strava=True)
    before = _default_gear_row(factory)

    with factory() as db:
        gear_service.delete_all_strava_gear_for_user(1, db)
        db.commit()

    after = _default_gear_row(factory)
    assert after.version == before.version + 1
    assert (after.run_gear_id, after.ride_gear_id) == (None, ride_id)
