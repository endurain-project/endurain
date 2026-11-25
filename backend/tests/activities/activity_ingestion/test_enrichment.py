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


class TestAMultisportFile:
    def test_gives_the_parent_the_privacy_defaults_and_no_gear_while_the_legs_take_their_types_default_gear(
        self, owner, pool, committed_sessions
    ):
        owner, shoes_id = owner
        _upload(owner, fit_file(activities=2, multisport=True), "triathlon.fit")
        pool.drain()

        rows = activities_of(committed_sessions, owner.user.id)
        [parent] = [row for row in rows if row.parent_activity_id is None]
        legs = [row for row in rows if row.parent_activity_id is not None]
        assert parent.gear_id is None
        assert [leg.gear_id for leg in legs] == [shoes_id, shoes_id]
        for row in rows:
            assert row.hide_location is True
            assert row.visibility == activity_constants.ActivityVisibility.FOLLOWERS.stored

    def test_from_garmin_carries_the_providers_id_on_the_parent_and_each_leg_and_no_activity_gear_on_any(
        self, owner, committed_sessions, tmp_path
    ):
        owner, shoes_id = owner
        with committed_sessions() as db:
            synced_gear = make_gear(db, owner.user.id, nickname="Synced shoes", gear_type="shoes")
            db.commit()
        path = tmp_path / "555_ACTIVITY.fit"
        path.write_bytes(fit_file(activities=2, multisport=True))

        with committed_sessions() as db:
            created = ingestion_integration.ingest_activity_file(
                owner.user.id,
                str(path),
                db,
                source=ingestion_integration.GarminSource(
                    activity_id=555, gear_id=synced_gear.id, provider_gear_id="garmin-gear-1"
                ),
            )

        assert created is not None
        rows = activities_of(committed_sessions, owner.user.id)
        [parent] = [row for row in rows if row.parent_activity_id is None]
        legs = [row for row in rows if row.parent_activity_id is not None]
        assert [(row.garminconnect_activity_id) for row in rows] == [555, 555, 555]
        assert (parent.gear_id, parent.garminconnect_gear_id) == (None, None)
        assert [(leg.gear_id, leg.garminconnect_gear_id) for leg in legs] == [(shoes_id, None)] * 2

    def test_from_garmin_gives_each_leg_its_own_gear_and_the_default_to_a_leg_without(
        self, owner, committed_sessions, tmp_path
    ):
        owner, shoes_id = owner
        with committed_sessions() as db:
            first = make_gear(db, owner.user.id, nickname="First", gear_type="shoes")
            third = make_gear(db, owner.user.id, nickname="Third", gear_type="shoes")
            db.commit()
        path = tmp_path / "555_ACTIVITY.fit"
        path.write_bytes(fit_file(activities=3, multisport=True))
        leg_gear = (
            ingestion_integration.LegGear(gear_id=first.id, provider_gear_id="garmin-first"),
            ingestion_integration.LegGear(),
            ingestion_integration.LegGear(gear_id=third.id, provider_gear_id="garmin-third"),
        )

        with committed_sessions() as db:
            ingestion_integration.ingest_activity_file(
                owner.user.id,
                str(path),
                db,
                source=ingestion_integration.GarminSource(activity_id=555, leg_gear=leg_gear),
            )

        rows = activities_of(committed_sessions, owner.user.id)
        [parent] = [row for row in rows if row.parent_activity_id is None]
        legs = sorted((row for row in rows if row.parent_activity_id is not None), key=lambda row: row.start_time)
        assert (parent.gear_id, parent.garminconnect_gear_id) == (None, None)
        assert [(leg.gear_id, leg.garminconnect_gear_id) for leg in legs] == [
            (first.id, "garmin-first"),
            (shoes_id, None),
            (third.id, "garmin-third"),
        ]

    # No leg gear at all means Garmin named no legs for a multisport activity: as unexpected as another count.
    @pytest.mark.parametrize("gear_count", [2, 0])
    def test_from_garmin_with_another_count_of_leg_gear_gives_no_leg_garmin_gear_and_logs_it_once(
        self, owner, committed_sessions, tmp_path, caplog, gear_count
    ):
        owner, shoes_id = owner
        with committed_sessions() as db:
            first = make_gear(db, owner.user.id, nickname="First", gear_type="shoes")
            db.commit()
        path = tmp_path / "555_ACTIVITY.fit"
        path.write_bytes(fit_file(activities=3, multisport=True))
        leg_gear = (ingestion_integration.LegGear(gear_id=first.id, provider_gear_id="garmin-first"),) * gear_count

        with caplog.at_level("WARNING"), committed_sessions() as db:
            ingestion_integration.ingest_activity_file(
                owner.user.id,
                str(path),
                db,
                source=ingestion_integration.GarminSource(activity_id=555, leg_gear=leg_gear),
            )

        legs = [row for row in activities_of(committed_sessions, owner.user.id) if row.parent_activity_id]
        assert [(leg.gear_id, leg.garminconnect_gear_id) for leg in legs] == [(shoes_id, None)] * 3
        [record] = [r for r in caplog.records if "leg gear" in r.getMessage()]
        assert (record.activity_id, record.leg_gear_count, record.leg_count) == (555, gear_count, 3)


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
                source=ingestion_integration.GarminSource(
                    activity_id=555, gear_id=synced_gear.id, provider_gear_id="garmin-gear-1"
                ),
            )

        assert created is not None
        (activity,) = activities_of(committed_sessions, owner.user.id)
        assert (activity.garminconnect_activity_id, activity.garminconnect_gear_id) == (555, "garmin-gear-1")
        assert activity.gear_id == synced_gear.id

    def test_takes_the_activity_id_from_the_source_not_the_file_name(self, owner, committed_sessions, tmp_path):
        owner, _shoes = owner
        path = tmp_path / "ride.gpx"
        path.write_bytes(activity_gpx())

        with committed_sessions() as db:
            created = ingestion_integration.ingest_activity_file(
                owner.user.id, str(path), db, source=ingestion_integration.GarminSource(activity_id=777)
            )

        assert created is not None
        (activity,) = activities_of(committed_sessions, owner.user.id)
        assert activity.garminconnect_activity_id == 777
