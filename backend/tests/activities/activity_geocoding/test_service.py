"""Tests for the activity location service.

Scoped to what this module owns: *when* a location is resolved and *where* it is
stored. How resolution happens is the platform's ``GeocodingProvider`` — the
provider request building, SSRF host validation, throttling and response parsing
are covered in ``tests/core/test_platform_geocoding.py``.
"""

from unittest.mock import MagicMock, patch

from infra.providers import GeocodedPlace
from modules.activities.activity_geocoding.service import (
    backfill_missing_activity_locations,
    geocode_and_store_activity_location,
    reverse_geocode,
)

_SVC = "modules.activities.activity_geocoding.service"


def _platform_returning(place: GeocodedPlace | None):
    """A patched platform whose geocoding provider resolves ``place``."""
    platform = MagicMock()
    platform.geocoding.reverse.return_value = place
    return patch(f"{_SVC}.platform_runtime.get_active_platform", return_value=platform)


class TestReverseGeocode:
    """The thin delegation to the platform provider."""

    def test_missing_latitude_skips_the_provider(self):
        with _platform_returning(None) as platform:
            assert reverse_geocode(None, -9.0) is None
        platform.return_value.geocoding.reverse.assert_not_called()

    def test_missing_longitude_skips_the_provider(self):
        with _platform_returning(None) as platform:
            assert reverse_geocode(38.0, None) is None
        platform.return_value.geocoding.reverse.assert_not_called()

    def test_delegates_coordinates_to_the_provider(self):
        place = GeocodedPlace(city="Lisbon", town="Belem", country="Portugal")
        with _platform_returning(place) as platform:
            assert reverse_geocode(38.0, -9.0) == place
        platform.return_value.geocoding.reverse.assert_called_once_with(38.0, -9.0)

    def test_unresolved_location_is_passed_through(self):
        with _platform_returning(None):
            assert reverse_geocode(38.0, -9.0) is None


class TestGeocodeAndStore:
    """The create-path store helper."""

    @patch(f"{_SVC}.activity_streams_service.get_stream_for_derivation", return_value=None)
    @patch(f"{_SVC}.activities_service.set_activity_location")
    def test_no_stream_returns_false(self, mock_update, _mock_stream):
        assert geocode_and_store_activity_location(1, 2, MagicMock()) is False
        mock_update.assert_not_called()

    @patch(f"{_SVC}.activity_streams_service.get_stream_for_derivation")
    @patch(f"{_SVC}.activities_service.set_activity_location")
    def test_empty_waypoints_returns_false(self, mock_update, mock_stream):
        mock_stream.return_value = MagicMock(stream_waypoints=[])
        assert geocode_and_store_activity_location(1, 2, MagicMock()) is False
        mock_update.assert_not_called()

    @patch(f"{_SVC}.reverse_geocode", return_value=None)
    @patch(f"{_SVC}.activity_streams_service.get_stream_for_derivation")
    @patch(f"{_SVC}.activities_service.set_activity_location")
    def test_unresolved_location_returns_false(self, mock_update, mock_stream, _mock_geo):
        mock_stream.return_value = MagicMock(stream_waypoints=[{"lat": 1.0, "lon": 2.0}])
        assert geocode_and_store_activity_location(1, 2, MagicMock()) is False
        mock_update.assert_not_called()

    @patch(f"{_SVC}.reverse_geocode", return_value=GeocodedPlace("Lisbon", "Belem", "Portugal"))
    @patch(f"{_SVC}.activity_streams_service.get_stream_for_derivation")
    @patch(f"{_SVC}.activities_service.set_activity_location")
    def test_success_stores_location(self, mock_update, mock_stream, _mock_geo):
        db = MagicMock()
        mock_stream.return_value = MagicMock(stream_waypoints=[{"lat": 38.0, "lon": -9.0}])
        assert geocode_and_store_activity_location(42, 7, db) is True
        mock_update.assert_called_once_with(42, "Lisbon", "Belem", "Portugal", db)

    @patch(f"{_SVC}.reverse_geocode")
    @patch(f"{_SVC}.activity_streams_service.get_stream_for_derivation")
    @patch(f"{_SVC}.activities_service.set_activity_location")
    def test_geocodes_the_first_waypoint(self, _mock_update, mock_stream, mock_geo):
        mock_stream.return_value = MagicMock(stream_waypoints=[{"lat": 38.0, "lon": -9.0}, {"lat": 40.0, "lon": -8.0}])
        geocode_and_store_activity_location(42, 7, MagicMock())
        mock_geo.assert_called_once_with(38.0, -9.0)


class TestBackfill:
    """The reconciliation backfill."""

    @patch(f"{_SVC}.activities_service.list_activities_missing_location", return_value=[])
    def test_no_candidates_returns_zero(self, _mock_candidates):
        assert backfill_missing_activity_locations(MagicMock()) == 0

    @patch(f"{_SVC}.reverse_geocode", return_value=GeocodedPlace("Lisbon", None, "Portugal"))
    @patch(f"{_SVC}.activity_streams_service.get_gps_waypoints_for_activities")
    @patch(f"{_SVC}.activities_service.list_activities_missing_location")
    @patch(f"{_SVC}.activities_service.set_activity_location")
    def test_stores_for_gps_candidates(self, mock_update, mock_candidates, mock_waypoints, _mock_geo):
        db = MagicMock()
        mock_candidates.return_value = [
            MagicMock(id=1),
            MagicMock(id=2),  # no GPS -> skipped
        ]
        mock_waypoints.return_value = {1: [{"lat": 38.0, "lon": -9.0}]}
        stored = backfill_missing_activity_locations(db)
        assert stored == 1
        mock_update.assert_called_once_with(1, "Lisbon", None, "Portugal", db)

    @patch(f"{_SVC}.reverse_geocode")
    @patch(f"{_SVC}.activity_streams_service.get_gps_waypoints_for_activities")
    @patch(f"{_SVC}.activities_service.list_activities_missing_location")
    @patch(f"{_SVC}.activities_service.set_activity_location")
    def test_skips_empty_waypoints(self, mock_update, mock_candidates, mock_waypoints, mock_geo):
        mock_candidates.return_value = [MagicMock(id=1)]
        mock_waypoints.return_value = {1: []}
        assert backfill_missing_activity_locations(MagicMock()) == 0
        mock_geo.assert_not_called()
        mock_update.assert_not_called()

    @patch(f"{_SVC}.reverse_geocode", return_value=None)
    @patch(f"{_SVC}.activity_streams_service.get_gps_waypoints_for_activities")
    @patch(f"{_SVC}.activities_service.list_activities_missing_location")
    @patch(f"{_SVC}.activities_service.set_activity_location")
    def test_unresolved_candidates_are_left_for_the_next_pass(
        self, mock_update, mock_candidates, mock_waypoints, _mock_geo
    ):
        mock_candidates.return_value = [MagicMock(id=1)]
        mock_waypoints.return_value = {1: [{"lat": 38.0, "lon": -9.0}]}
        assert backfill_missing_activity_locations(MagicMock()) == 0
        mock_update.assert_not_called()
