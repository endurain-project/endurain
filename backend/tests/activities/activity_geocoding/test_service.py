"""Locating activities from their GPS stream, against a real database and a real reverse-geocoding service."""

from datetime import timedelta

import jasil.runtime as platform_runtime
import pytest
from sqlalchemy import delete as delete_statement

import modules.activities.activity.models as activity_models
import modules.activities.activity_geocoding.service as geocoding_service
import modules.activities.activity_streams.constants as stream_constants
from tests._factories.activities import DEFAULT_START, make_activity, make_stream
from tests._factories.users import make_user

_MAP = stream_constants.STREAM_TYPE_MAP
_LISBON = [{"lat": 38.7, "lon": -9.1}, {"lat": 38.8, "lon": -9.2}]
_MATOSINHOS = [{"lat": 41.2, "lon": -8.7}]
_NOWHERE = [{"lat": 0.5, "lon": 0.5}]


@pytest.fixture
def clock():
    return platform_runtime.get_active_platform().clock


@pytest.fixture
def owner(db):
    return make_user(db)


def _activity(db, owner, route=None, day: int = 0, **fields):
    start = DEFAULT_START + timedelta(days=day)
    activity = make_activity(db, owner.id, start_time=start, end_time=start + timedelta(hours=1), **fields)
    if route is not None:
        make_stream(db, activity, _MAP, route)
    return activity


def _place(db, activity) -> tuple[str | None, str | None, str | None]:
    db.expire_all()
    row = db.get(activity_models.Activity, activity.id)
    return row.city, row.town, row.country


class TestReverseGeocode:
    def test_a_coordinate_is_resolved_to_a_place_by_the_service(self, geocoder, geocoding_server):
        outcome = geocoding_service.reverse_geocode(geocoder, 38.7, -9.1)

        assert (outcome.place.locality, outcome.place.sublocality, outcome.place.country) == (
            "Lisbon",
            "Alvalade",
            "Portugal",
        )
        assert outcome.retry_at is None
        assert (geocoding_server.requests[0]["lat"], geocoding_server.requests[0]["lon"]) == ("38.7", "-9.1")

    @pytest.mark.parametrize(("latitude", "longitude"), [(None, 1.0), (1.0, None), (None, None)])
    def test_a_missing_coordinate_is_a_final_nothing_and_asks_the_service_nothing(
        self, geocoder, geocoding_server, latitude, longitude
    ):
        outcome = geocoding_service.reverse_geocode(geocoder, latitude, longitude)

        assert (outcome.place, outcome.retry_at, geocoding_server.requests) == (None, None, [])

    def test_a_place_the_service_does_not_know_is_a_final_nothing(self, geocoder):
        outcome = geocoding_service.reverse_geocode(geocoder, 0.5, 0.5)

        assert (outcome.place, outcome.retry_at) == (None, None)

    def test_a_rate_limited_service_says_when_to_ask_again(self, geocoder, geocoding_server, clock):
        geocoding_server.mode = "rate_limited"

        outcome = geocoding_service.reverse_geocode(geocoder, 38.7, -9.1)

        assert outcome.place is None
        assert outcome.retry_at == clock.now() + timedelta(seconds=120)

    def test_a_service_that_is_down_says_to_ask_again_later_and_never_raises(self, geocoder, geocoding_server, clock):
        geocoding_server.mode = "broken"

        outcome = geocoding_service.reverse_geocode(geocoder, 38.7, -9.1)

        assert outcome.place is None and outcome.retry_at > clock.now()

    def test_without_a_configured_service_nothing_resolves(self, db):
        outcome = geocoding_service.reverse_geocode(platform_runtime.get_active_platform().geocoding, 38.7, -9.1)

        assert (outcome.place, outcome.retry_at) == (None, None)


class TestGeocodeOneActivity:
    def test_the_first_gps_point_of_the_activity_locates_it(self, db, owner, geocoder, geocoding_server):
        activity = _activity(db, owner, _LISBON)

        retry_at = geocoding_service.geocode_and_store_activity_location(activity.id, geocoder, db)

        assert retry_at is None
        assert _place(db, activity) == ("Lisbon", "Alvalade", "Portugal")
        assert [r["lat"] for r in geocoding_server.requests] == ["38.7"]

    def test_a_town_without_a_city_is_stored_as_the_locality(self, db, owner, geocoder):
        activity = _activity(db, owner, _MATOSINHOS)

        geocoding_service.geocode_and_store_activity_location(activity.id, geocoder, db)

        assert _place(db, activity) == ("Matosinhos", None, "Portugal")

    @pytest.mark.parametrize("route", [None, []])
    def test_an_activity_without_a_gps_stream_or_points_asks_the_service_nothing(
        self, db, owner, geocoder, geocoding_server, route
    ):
        activity = _activity(db, owner, route)

        assert geocoding_service.geocode_and_store_activity_location(activity.id, geocoder, db) is None

        assert (_place(db, activity), geocoding_server.requests) == ((None, None, None), [])

    def test_a_place_the_service_does_not_know_stores_nothing_and_asks_for_no_retry(self, db, owner, geocoder):
        activity = _activity(db, owner, _NOWHERE)

        assert geocoding_service.geocode_and_store_activity_location(activity.id, geocoder, db) is None

        assert _place(db, activity) == (None, None, None)

    def test_a_held_back_lookup_stores_nothing_and_returns_when_to_ask_again(
        self, db, owner, geocoder, geocoding_server, clock
    ):
        geocoding_server.mode = "rate_limited"
        activity = _activity(db, owner, _LISBON)

        retry_at = geocoding_service.geocode_and_store_activity_location(activity.id, geocoder, db)

        assert retry_at == clock.now() + timedelta(seconds=120)
        assert _place(db, activity) == (None, None, None)


class TestActivityDeletedWhileLocating:
    """The activity can be deleted while the service is still answering; nothing is written for it."""

    @pytest.fixture
    def committed_routes(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            activities = [_activity(db, user, _LISBON, day) for day in range(2)]
            db.commit()
        return activities

    @staticmethod
    def _delete_on_request(committed_sessions, geocoding_server, activity_id):
        def delete() -> None:
            with committed_sessions() as other:
                other.execute(
                    delete_statement(activity_models.Activity).where(activity_models.Activity.id == activity_id)
                )
                other.commit()

        geocoding_server.on_request = delete

    def test_a_single_lookup_for_an_activity_deleted_meanwhile_writes_nothing_and_asks_for_no_retry(
        self, committed_sessions, committed_routes, geocoder, geocoding_server
    ):
        gone = committed_routes[0]
        self._delete_on_request(committed_sessions, geocoding_server, gone.id)

        with committed_sessions() as db:
            retry_at = geocoding_service.geocode_and_store_activity_location(gone.id, geocoder, db)

        assert retry_at is None
        with committed_sessions() as db:
            assert db.get(activity_models.Activity, gone.id) is None

    def test_a_backfill_pass_skips_an_activity_deleted_meanwhile_and_locates_the_others(
        self, committed_sessions, committed_routes, geocoder, geocoding_server
    ):
        gone, kept = committed_routes
        self._delete_on_request(committed_sessions, geocoding_server, gone.id)

        with committed_sessions() as db:
            stored = geocoding_service.backfill_missing_activity_locations(
                geocoder, platform_runtime.get_active_platform().clock, db
            )

        assert stored == 1
        with committed_sessions() as db:
            assert db.get(activity_models.Activity, kept.id).country == "Portugal"


class TestBackfill:
    def test_every_gps_activity_without_a_place_is_located_and_the_count_is_returned(self, db, owner, geocoder, clock):
        lisbon, matosinhos = _activity(db, owner, _LISBON, 0), _activity(db, owner, _MATOSINHOS, 1)

        stored = geocoding_service.backfill_missing_activity_locations(geocoder, clock, db)

        assert stored == 2
        assert _place(db, lisbon)[2] == "Portugal" and _place(db, matosinhos)[0] == "Matosinhos"

    def test_a_lookup_waits_for_its_turn_under_the_rate_limit_instead_of_ending_the_pass(
        self, db, owner, paced_geocoder, clock
    ):
        lisbon, matosinhos = _activity(db, owner, _LISBON, 0), _activity(db, owner, _MATOSINHOS, 1)

        stored = geocoding_service.backfill_missing_activity_locations(paced_geocoder, clock, db)

        assert stored == 2
        assert _place(db, lisbon)[2] == "Portugal" and _place(db, matosinhos)[0] == "Matosinhos"

    def test_an_activity_that_already_has_a_place_is_left_alone(self, db, owner, geocoder, geocoding_server, clock):
        located = _activity(db, owner, _LISBON, 0, city="Elsewhere")

        assert geocoding_service.backfill_missing_activity_locations(geocoder, clock, db) == 0

        assert (_place(db, located)[0], geocoding_server.requests) == ("Elsewhere", [])

    def test_activities_with_no_route_or_no_known_place_wait_a_day_before_they_are_looked_up_again(
        self, db, owner, geocoder, geocoding_server, clock
    ):
        bare, unknown = _activity(db, owner, None, 0), _activity(db, owner, _NOWHERE, 1)

        first = geocoding_service.backfill_missing_activity_locations(geocoder, clock, db)
        asked = len(geocoding_server.requests)
        again = geocoding_service.backfill_missing_activity_locations(geocoder, clock, db)
        clock.advance(geocoding_service.LOOKUP_RETRY_DELAY.total_seconds() + 1)
        make_stream(db, bare, _MAP, _LISBON)
        later = geocoding_service.backfill_missing_activity_locations(geocoder, clock, db)

        assert (first, asked, again, len(geocoding_server.requests)) == (0, 1, 0, 3)
        assert (later, _place(db, bare)[0], _place(db, unknown)) == (1, "Lisbon", (None, None, None))

    def test_a_held_back_lookup_ends_the_pass_and_leaves_the_activity_due(
        self, db, owner, geocoder, geocoding_server, clock
    ):
        geocoding_server.mode = "rate_limited"
        first, second = _activity(db, owner, _LISBON, 0), _activity(db, owner, _LISBON, 1)

        assert geocoding_service.backfill_missing_activity_locations(geocoder, clock, db) == 0
        calls = len(geocoding_server.requests)
        geocoding_server.mode = "ok"
        clock.advance(121)
        stored = geocoding_service.backfill_missing_activity_locations(geocoder, clock, db)

        assert calls == 1
        assert stored == 2 and _place(db, first)[0] == "Lisbon" and _place(db, second)[0] == "Lisbon"

    def test_a_pass_makes_no_more_lookups_than_its_budget_and_the_next_pass_carries_on(
        self, db, owner, geocoder, geocoding_server, clock
    ):
        for day in range(3):
            _activity(db, owner, _LISBON, day)

        first = geocoding_service.backfill_missing_activity_locations(geocoder, clock, db, max_lookups=2)
        second = geocoding_service.backfill_missing_activity_locations(geocoder, clock, db, max_lookups=2)

        assert (first, second, len(geocoding_server.requests)) == (2, 1, 3)

    def test_a_pass_with_nothing_to_locate_asks_the_service_nothing(self, db, geocoder, geocoding_server, clock):
        assert geocoding_service.backfill_missing_activity_locations(geocoder, clock, db) == 0
        assert geocoding_server.requests == []
