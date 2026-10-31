"""Tests for the activity location service.

Scoped to what this module owns: *when* a location is resolved and *where* it is
stored. How resolution happens is the platform's ``GeocodingProvider`` — the
provider request building, SSRF host validation, throttling and response parsing
are covered in ``tests/core/test_platform_geocoding.py``.
"""

import inspect
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from jasil.providers import GeocodedPlace

from modules.activities.activity_geocoding.service import (
    LOOKUP_RETRY_DELAY,
    backfill_missing_activity_locations,
    geocode_and_store_activity_location,
    reverse_geocode,
)

_SVC = "modules.activities.activity_geocoding.service"


def _provider_returning(place: GeocodedPlace | None) -> MagicMock:
    """A geocoding provider double that resolves ``place``."""
    provider = MagicMock()
    provider.reverse.return_value = place
    return provider


class TestReverseGeocode:
    """The thin delegation to the platform provider."""

    def test_missing_latitude_skips_the_provider(self):
        provider = _provider_returning(None)
        assert reverse_geocode(provider, None, -9.0) is None
        provider.reverse.assert_not_called()

    def test_missing_longitude_skips_the_provider(self):
        provider = _provider_returning(None)
        assert reverse_geocode(provider, 38.0, None) is None
        provider.reverse.assert_not_called()

    def test_delegates_coordinates_to_the_provider(self):
        place = GeocodedPlace(city="Lisbon", town="Belem", country="Portugal")
        provider = _provider_returning(place)
        assert reverse_geocode(provider, 38.0, -9.0) == place
        provider.reverse.assert_called_once_with(38.0, -9.0)

    def test_unresolved_location_is_passed_through(self):
        assert reverse_geocode(_provider_returning(None), 38.0, -9.0) is None


class TestGeocodeAndStore:
    """The create-path store helper."""

    def test_contract_takes_activity_session_and_provider(self):
        assert tuple(inspect.signature(geocode_and_store_activity_location).parameters) == (
            "activity_id",
            "geocoding",
            "db",
        )

    @patch(f"{_SVC}.activity_streams_integration.get_stream_for_derivation", return_value=None)
    @patch(f"{_SVC}.activity_integration.set_activity_location")
    def test_no_stream_returns_false(self, mock_update, _mock_stream):
        assert geocode_and_store_activity_location(1, MagicMock(), MagicMock()) is False
        mock_update.assert_not_called()

    @patch(f"{_SVC}.activity_streams_integration.get_stream_for_derivation")
    @patch(f"{_SVC}.activity_integration.set_activity_location")
    def test_empty_waypoints_returns_false(self, mock_update, mock_stream):
        mock_stream.return_value = MagicMock(stream_waypoints=[])
        assert geocode_and_store_activity_location(1, MagicMock(), MagicMock()) is False
        mock_update.assert_not_called()

    @patch(f"{_SVC}.reverse_geocode", return_value=None)
    @patch(f"{_SVC}.activity_streams_integration.get_stream_for_derivation")
    @patch(f"{_SVC}.activity_integration.set_activity_location")
    def test_unresolved_location_returns_false(self, mock_update, mock_stream, _mock_geo):
        mock_stream.return_value = MagicMock(stream_waypoints=[{"lat": 1.0, "lon": 2.0}])
        assert geocode_and_store_activity_location(1, MagicMock(), MagicMock()) is False
        mock_update.assert_not_called()

    @patch(f"{_SVC}.reverse_geocode", return_value=GeocodedPlace("Lisbon", "Belem", "Portugal"))
    @patch(f"{_SVC}.activity_streams_integration.get_stream_for_derivation")
    @patch(f"{_SVC}.activity_integration.set_activity_location")
    def test_success_stores_location(self, mock_update, mock_stream, _mock_geo):
        db = MagicMock()
        mock_stream.return_value = MagicMock(stream_waypoints=[{"lat": 38.0, "lon": -9.0}])
        assert geocode_and_store_activity_location(42, MagicMock(), db) is True
        mock_update.assert_called_once_with(42, "Lisbon", "Belem", "Portugal", db)
        # The surface only stages; the geocoding service owns the commit.
        # One commit ends the read transaction before the geocoder call, one persists the result.
        assert db.commit.call_count == 2

    @patch(f"{_SVC}.reverse_geocode", return_value=GeocodedPlace("Lisbon", "Belem", "Portugal"))
    @patch(f"{_SVC}.activity_streams_integration.get_stream_for_derivation")
    @patch(f"{_SVC}.activity_integration.set_activity_location", return_value=False)
    def test_does_not_commit_when_no_row_changed(self, _mock_update, mock_stream, _mock_geo):
        db = MagicMock()
        mock_stream.return_value = MagicMock(stream_waypoints=[{"lat": 38.0, "lon": -9.0}])
        geocode_and_store_activity_location(999, MagicMock(), db)
        # Only the read transaction is ended before the lookup; nothing is persisted.
        assert db.commit.call_count == 1

    @patch(f"{_SVC}.reverse_geocode")
    @patch(f"{_SVC}.activity_streams_integration.get_stream_for_derivation")
    @patch(f"{_SVC}.activity_integration.set_activity_location")
    def test_geocodes_the_first_waypoint(self, _mock_update, mock_stream, mock_geo):
        mock_stream.return_value = MagicMock(stream_waypoints=[{"lat": 38.0, "lon": -9.0}, {"lat": 40.0, "lon": -8.0}])
        provider = MagicMock()
        geocode_and_store_activity_location(42, provider, MagicMock())
        mock_geo.assert_called_once_with(provider, 38.0, -9.0)


_NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def _clock() -> MagicMock:
    clock = MagicMock()
    clock.now.return_value = _NOW
    return clock


@patch(f"{_SVC}.activity_integration.defer_location_lookups")
@patch(f"{_SVC}.activity_integration.set_activity_location")
@patch(f"{_SVC}.activity_integration.list_activities_missing_location")
@patch(f"{_SVC}.activity_streams_integration.get_gps_waypoints_for_activities")
@patch(f"{_SVC}.reverse_geocode")
class TestBackfill:
    """The reconciliation backfill."""

    def test_no_candidates_returns_zero(self, _geo, _waypoints, mock_candidates, _update, mock_defer):
        mock_candidates.return_value = []

        assert backfill_missing_activity_locations(MagicMock(), _clock(), MagicMock()) == 0
        mock_defer.assert_not_called()

    def test_only_due_activities_are_listed(self, _geo, _waypoints, mock_candidates, _update, _defer):
        mock_candidates.return_value = []

        backfill_missing_activity_locations(MagicMock(), _clock(), MagicMock())

        assert mock_candidates.call_args.kwargs["due_at"] == _NOW

    def test_stores_a_resolved_location(self, mock_geo, mock_waypoints, mock_candidates, mock_update, mock_defer):
        db = MagicMock()
        mock_candidates.side_effect = [[MagicMock(id=1)], []]
        mock_waypoints.return_value = {1: [{"lat": 38.0, "lon": -9.0}]}
        mock_geo.return_value = GeocodedPlace("Lisbon", None, "Portugal")

        assert backfill_missing_activity_locations(MagicMock(), _clock(), db) == 1
        mock_update.assert_called_once_with(1, "Lisbon", None, "Portugal", db)
        # One commit ends the read transaction before the lookups, one persists the result.
        assert db.commit.call_count == 2
        mock_defer.assert_not_called()

    def test_an_activity_without_gps_is_deferred_without_a_lookup(
        self, mock_geo, mock_waypoints, mock_candidates, _update, mock_defer
    ):
        db = MagicMock()
        mock_candidates.side_effect = [[MagicMock(id=1), MagicMock(id=2)], []]
        mock_waypoints.return_value = {1: []}

        backfill_missing_activity_locations(MagicMock(), _clock(), db)

        mock_geo.assert_not_called()
        mock_defer.assert_called_once_with([1, 2], _NOW + LOOKUP_RETRY_DELAY, db)

    @pytest.mark.parametrize("place", [None, GeocodedPlace(None, None, None)], ids=["nothing", "empty_place"])
    def test_a_lookup_that_resolves_nothing_is_deferred(
        self, mock_geo, mock_waypoints, mock_candidates, mock_update, mock_defer, place
    ):
        """Open sea, a disabled provider or an outage: retried after the delay, never given up on."""
        db = MagicMock()
        mock_candidates.side_effect = [[MagicMock(id=1)], []]
        mock_waypoints.return_value = {1: [{"lat": 0.0, "lon": -30.0}]}
        mock_geo.return_value = place

        assert backfill_missing_activity_locations(MagicMock(), _clock(), db) == 0
        mock_update.assert_not_called()
        mock_defer.assert_called_once_with([1], _NOW + LOOKUP_RETRY_DELAY, db)

    def test_does_not_count_a_row_that_did_not_change(
        self, mock_geo, mock_waypoints, mock_candidates, mock_update, _defer
    ):
        """An activity deleted between listing and writing is neither stored nor committed."""
        db = MagicMock()
        mock_candidates.side_effect = [[MagicMock(id=1)], []]
        mock_waypoints.return_value = {1: [{"lat": 38.0, "lon": -9.0}]}
        mock_geo.return_value = GeocodedPlace("Lisbon", None, "Portugal")
        mock_update.return_value = False

        assert backfill_missing_activity_locations(MagicMock(), _clock(), db) == 0
        # Only the read transaction is ended before the lookups; the row did not change.
        assert db.commit.call_count == 1

    def test_pages_past_activities_that_cannot_resolve(
        self, mock_geo, mock_waypoints, mock_candidates, mock_update, _defer
    ):
        db = MagicMock()
        mock_candidates.side_effect = [[MagicMock(id=1), MagicMock(id=2)], [MagicMock(id=3)], []]
        mock_waypoints.side_effect = [{}, {3: [{"lat": 38.0, "lon": -9.0}]}]
        mock_geo.return_value = GeocodedPlace("Lisbon", None, "Portugal")

        assert backfill_missing_activity_locations(MagicMock(), _clock(), db) == 1
        mock_update.assert_called_once_with(3, "Lisbon", None, "Portugal", db)
        assert [call.kwargs["after_id"] for call in mock_candidates.call_args_list] == [0, 2, 3]

    def test_lookups_are_capped_and_the_rest_stay_due(
        self, mock_geo, mock_waypoints, mock_candidates, _update, mock_defer
    ):
        db = MagicMock()
        mock_candidates.side_effect = [[MagicMock(id=1), MagicMock(id=2), MagicMock(id=3)], []]
        mock_waypoints.return_value = {
            1: [{"lat": 1.0, "lon": 1.0}],
            2: [{"lat": 2.0, "lon": 2.0}],
            3: [{"lat": 3.0, "lon": 3.0}],
        }
        mock_geo.return_value = None

        backfill_missing_activity_locations(MagicMock(), _clock(), db, max_lookups=2)

        assert mock_geo.call_count == 2
        # Activity 3 was never looked up, so it is not pushed back.
        mock_defer.assert_called_once_with([1, 2], _NOW + LOOKUP_RETRY_DELAY, db)
