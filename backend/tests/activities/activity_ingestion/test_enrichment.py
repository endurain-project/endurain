"""An imported activity carries its owner's privacy defaults and default gear, whichever route it came in by."""

import pytest

import core.config as core_config
import modules.activities.activity.constants as activity_constants
import modules.activities.activity_ingestion.integration_service as ingestion_integration
from tests._factories.garmin import activity_gpx
from tests._factories.gears import make_gear
from tests._factories.ingestion import StubProvider, activities_of, fit_file, set_default_gear, set_privacy_defaults
from tests._factories.users import make_user

_API = core_config.ROOT_PATH


@pytest.fixture
def owner(committed_sessions, sign_in):
    """A signed-in user whose location is hidden by default, whose activities are visible to followers and whose runs
    are on a pair of shoes: ``(signed in user, shoes id)``."""
    with committed_sessions() as db:
        user = make_user(db, timezone="UTC")
        shoes = make_gear(db, user.id, nickname="Trail shoes", gear_type="shoes")
        set_privacy_defaults(db, user.id, hide_activity_location=True, default_activity_visibility="followers")
        set_default_gear(db, user.id, run_gear_id=shoes.id)
        db.commit()
    return sign_in(user), shoes.id


def _upload(user, content: bytes, name: str):
    return user.client.post(f"{_API}/activities/upload", files={"file": (name, content)})


class TestAnUploadedActivity:
    def test_takes_the_owners_privacy_defaults(self, owner, pool, committed_sessions):
        owner, _shoes = owner
        _upload(owner, activity_gpx(), "ride.gpx")
        pool.drain()

        (activity,) = activities_of(committed_sessions, owner.user.id)
        assert activity.hide_location is True
        assert activity.hide_hr is False
        assert activity.visibility == activity_constants.ActivityVisibility.FOLLOWERS.stored

    def test_takes_the_default_gear_of_its_activity_type(self, owner, pool, committed_sessions):
        owner, shoes_id = owner
        _upload(owner, fit_file(), "run.fit")
        pool.drain()

        (activity,) = activities_of(committed_sessions, owner.user.id)
        assert activity.gear_id == shoes_id

    def test_has_no_gear_when_its_type_has_no_default(self, owner, pool, committed_sessions):
        owner, _shoes = owner
        _upload(owner, activity_gpx(), "ride.gpx")
        pool.drain()

        (activity,) = activities_of(committed_sessions, owner.user.id)
        assert activity.gear_id is None

    def test_a_user_who_changed_nothing_gets_the_stock_defaults(self, make_signed_in, pool, committed_sessions):
        plain = make_signed_in()
        _upload(plain, activity_gpx(), "ride.gpx")
        pool.drain()

        (activity,) = activities_of(committed_sessions, plain.user.id)
        assert activity.hide_location is False
        assert activity.visibility == activity_constants.ActivityVisibility.PRIVATE.stored


class TestAProviderSyncedActivity:
    def test_takes_the_owners_privacy_defaults_too(self, owner, providers, pool, committed_sessions):
        owner, _shoes = owner
        provider = StubProvider().register()
        provider.link(owner.user.id, activity_gpx())

        owner.client.post(f"{_API}/activities/refresh")
        pool.drain()

        (activity,) = activities_of(committed_sessions, owner.user.id)
        assert activity.hide_location is True


class TestAGarminFile:
    def test_carries_the_providers_ids_and_the_gear_the_provider_resolved_instead_of_the_default(
        self, owner, committed_sessions, tmp_path
    ):
        owner, _shoes = owner
        with committed_sessions() as db:
            synced_gear = make_gear(db, owner.user.id, nickname="Synced shoes", gear_type="shoes")
            db.commit()
        path = tmp_path / "555_ACTIVITY.gpx"
        path.write_bytes(activity_gpx())

        with committed_sessions() as db:
            created = ingestion_integration.ingest_activity_file(
                owner.user.id,
                str(path),
                db,
                source=ingestion_integration.GarminSource(gear_id=synced_gear.id, provider_gear_id="garmin-gear-1"),
            )

        assert created is not None
        (activity,) = activities_of(committed_sessions, owner.user.id)
        assert (activity.garminconnect_activity_id, activity.garminconnect_gear_id) == (555, "garmin-gear-1")
        assert activity.gear_id == synced_gear.id
