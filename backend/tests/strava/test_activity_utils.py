"""Tests for strava.activity_utils stream-fetching logic."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from stravalib.exc import Fault as StravaFault

import modules.strava.activity_utils as activity_utils
import modules.strava.utils as strava_utils

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_strava_fault(status_code: int) -> StravaFault:
    """Return a StravaFault whose .response.status_code equals *status_code*."""
    response = Mock()
    response.status_code = status_code
    fault = StravaFault()
    fault.response = response
    return fault


# ---------------------------------------------------------------------------
# fetch_and_process_activity_streams — empty-stream (404) path
# ---------------------------------------------------------------------------


class TestFetchAndProcessActivityStreamsNotFound:
    """Tests for the 404 / no-streams path in fetch_and_process_activity_streams."""

    def _call(self, client: Mock) -> tuple:
        return activity_utils.fetch_and_process_activity_streams(
            strava_client=client,
            strava_activity_id=99,
            user_id=1,
        )

    def test_not_found_fault_returns_empty_streams(self, monkeypatch):
        """A StravaFault 404 yields thirteen empty/False return values."""
        client = Mock()
        client.get_activity_streams.side_effect = _make_strava_fault(404)

        monkeypatch.setattr(strava_utils.rate_limit_tracker, "is_rate_limited", lambda: False)
        monkeypatch.setattr(activity_utils, "logger", Mock())

        result = self._call(client)

        assert result == (
            [],
            False,
            [],
            False,
            [],
            False,
            [],
            False,
            [],
            False,
            [],
            False,
            [],
        )

    def test_not_found_plain_exception_returns_empty_streams(self, monkeypatch):
        """A generic 'not found' exception also yields empty stream data."""
        client = Mock()
        client.get_activity_streams.side_effect = RuntimeError("404 not found")

        monkeypatch.setattr(strava_utils.rate_limit_tracker, "is_rate_limited", lambda: False)
        monkeypatch.setattr(activity_utils, "logger", Mock())

        result = self._call(client)

        assert result == (
            [],
            False,
            [],
            False,
            [],
            False,
            [],
            False,
            [],
            False,
            [],
            False,
            [],
        )

    def test_rate_limit_fault_raises_429(self, monkeypatch):
        """A StravaFault 429 raises HTTPException 429, not empty streams."""
        client = Mock()
        client.get_activity_streams.side_effect = _make_strava_fault(429)

        monkeypatch.setattr(strava_utils.rate_limit_tracker, "is_rate_limited", lambda: False)
        monkeypatch.setattr(strava_utils.rate_limit_tracker, "mark_rate_limited", Mock())
        monkeypatch.setattr(activity_utils, "logger", Mock())

        with pytest.raises(HTTPException) as exc_info:
            self._call(client)

        assert exc_info.value.status_code == 429

    def test_pre_check_rate_limited_raises_429(self, monkeypatch):
        """When already rate-limited, raises HTTPException 429 before any API call."""
        client = Mock()

        monkeypatch.setattr(strava_utils.rate_limit_tracker, "is_rate_limited", lambda: True)
        monkeypatch.setattr(activity_utils, "logger", Mock())

        with pytest.raises(HTTPException) as exc_info:
            self._call(client)

        assert exc_info.value.status_code == 429
        client.get_activity_streams.assert_not_called()

    def test_unrelated_exception_raises_424(self, monkeypatch):
        """An unrelated exception raises HTTPException 424."""
        client = Mock()
        client.get_activity_streams.side_effect = RuntimeError("network failure")

        monkeypatch.setattr(strava_utils.rate_limit_tracker, "is_rate_limited", lambda: False)
        monkeypatch.setattr(activity_utils, "logger", Mock())

        with pytest.raises(HTTPException) as exc_info:
            self._call(client)

        assert exc_info.value.status_code == 424


# ---------------------------------------------------------------------------
# save_activity_streams_laps — routes Strava sync through the ingestion seam
# ---------------------------------------------------------------------------


class TestSaveActivityStreamsLaps:
    """Strava persists through the canonical store_parsed_activity seam."""

    def test_builds_parsed_activity_and_delegates_to_seam(self, monkeypatch):
        """Only set streams are forwarded; laps and Strava provenance are carried."""
        import modules.activities.activity.schema as activity_schema

        captured: dict = {}

        def _fake_store(parsed, db):
            captured["parsed"] = parsed
            captured["db"] = db
            return activity_schema.ActivityRead(id=42, user_id=1, distance=0, name="X", activity_type=1)

        monkeypatch.setattr(activity_utils.activity_integration, "store_parsed_activity", _fake_store)

        activity = activity_schema.ActivityRead(
            id=1, user_id=1, distance=1000, name="Ride", activity_type=1, strava_activity_id=555
        )
        stream_data = [
            (True, 1, [{"hr": 140}]),
            (False, 2, [{"power": 200}]),  # not set -> excluded
            (True, 7, [{"lat": 1.0, "lon": 2.0}]),
        ]
        laps = [{"pace": 5.0}]
        db = Mock()

        result = activity_utils.save_activity_streams_laps(activity, stream_data, laps, db)

        assert result.id == 42
        parsed = captured["parsed"]
        assert [stream.stream_type for stream in parsed.components["streams"]] == [1, 7]
        assert parsed.components["laps"] == laps
        assert parsed.source.kind == "strava"
        assert parsed.source.provider_activity_id == 555
        assert captured["db"] is db

    def test_handles_empty_streams_and_no_laps(self, monkeypatch):
        """Empty stream_data and None laps yield an empty-stream, no-lap ParsedActivity."""
        import modules.activities.activity.schema as activity_schema

        captured: dict = {}

        def _fake_store(parsed, db):
            captured["parsed"] = parsed
            return activity_schema.ActivityRead(id=1, user_id=1, distance=0, name="X", activity_type=1)

        monkeypatch.setattr(activity_utils.activity_integration, "store_parsed_activity", _fake_store)

        activity = activity_schema.ActivityRead(id=1, user_id=1, distance=0, name="X", activity_type=1)
        activity_utils.save_activity_streams_laps(activity, [], None, Mock())

        parsed = captured["parsed"]
        assert parsed.components == {"streams": [], "laps": None}
        assert parsed.source.kind == "strava"


class _TrackingSession:
    """A ``SessionLocal`` stand-in that records how many sessions are open."""

    open_count = 0

    def __enter__(self):
        type(self).open_count += 1
        return Mock()

    def __exit__(self, *_exc):
        type(self).open_count -= 1
        return False


class TestProcessActivity:
    """Processing one Strava activity: no session is held while Strava is being called."""

    def _setup(self, monkeypatch, *, already_stored: bool = False):
        import modules.activities.activity.schema as activity_schema

        _TrackingSession.open_count = 0
        seen: dict[str, int] = {}
        monkeypatch.setattr(activity_utils, "SessionLocal", _TrackingSession)
        monkeypatch.setattr(
            activity_utils.strava_utils,
            "fetch_and_validate_activity",
            lambda *args, **kwargs: Mock() if already_stored else None,
        )

        def _fake_parse(*args, **kwargs):
            seen["during_parse"] = _TrackingSession.open_count
            return {"activity_to_store": Mock(), "stream_data": [], "laps": None}

        def _fake_save(*args, **kwargs):
            seen["during_save"] = _TrackingSession.open_count
            return activity_schema.ActivityRead(id=7, user_id=1, distance=0, name="X", activity_type=1)

        monkeypatch.setattr(activity_utils, "parse_activity", _fake_parse)
        monkeypatch.setattr(activity_utils, "save_activity_streams_laps", _fake_save)
        return seen

    def test_the_strava_calls_run_with_no_session_open(self, monkeypatch):
        """A transaction held across Strava round trips is what this was restructured to avoid."""
        seen = self._setup(monkeypatch)

        result = activity_utils.process_activity(Mock(id=555), 1, Mock(), Mock(), Mock())

        assert result.id == 7
        assert seen["during_parse"] == 0
        # The store gets its own short session.
        assert seen["during_save"] == 1

    def test_an_activity_already_stored_is_skipped_without_calling_strava(self, monkeypatch):
        seen = self._setup(monkeypatch, already_stored=True)

        assert activity_utils.process_activity(Mock(id=555), 1, Mock(), Mock(), Mock()) is None
        assert seen == {}


class TestFetchAndProcessActivityLapsElevation:
    """Lap ascent/descent computed from the Strava altitude stream."""

    def _lap(self) -> Mock:
        lap = Mock()
        lap.start_index = 0
        lap.end_index = 2
        lap.start_date_local = datetime(2025, 1, 1, 8, 0, 0)
        lap.average_heartrate = None
        lap.max_heartrate = None
        lap.average_speed = None
        lap.max_speed = None
        return lap

    def _process(self, ele_stream: list[dict]) -> dict:
        client = Mock()
        client.get_activity_laps.return_value = [self._lap()]
        laps = activity_utils.fetch_and_process_activity_laps(client, 1, 1, [(True, 4, ele_stream)])
        return laps[0]

    def test_invalid_altitude_stream_leaves_lap_elevation_none(self):
        """An altitude stream with no valid values yields None, not 0 m."""
        lap = self._process([{"ele": None}, {"ele": None}, {"ele": None}])

        assert lap["total_ascent"] is None
        assert lap["total_descent"] is None

    def test_flat_altitude_stream_stores_zero(self):
        """A flat altitude stream yields a genuine 0 m ascent/descent."""
        lap = self._process([{"ele": 100.0}, {"ele": 100.0}, {"ele": 100.0}])

        assert lap["total_ascent"] == 0
        assert lap["total_descent"] == 0
