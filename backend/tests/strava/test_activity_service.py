"""Tests for strava.activity_utils stream-fetching logic."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, Mock

import jasil.runtime as platform_runtime
import pytest
from stravalib.exc import AccessUnauthorized, ObjectNotFound
from stravalib.exc import Fault as StravaFault

import core.exceptions as core_exceptions
import modules.strava.activity_service as activity_utils
import modules.strava.client_service as strava_utils
import modules.strava.rate_limit_store as strava_rate_limit_store

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _integrations(client_id: str = "app-a") -> Mock:
    """Integrations whose (already plain) client id is *client_id*; decryption is the identity."""
    return Mock(strava_client_id=client_id)


@pytest.fixture
def rate_limits():
    return strava_rate_limit_store.StravaRateLimitStore(platform_runtime.get_state())


@pytest.fixture(autouse=True)
def _plain_client_id(monkeypatch):
    monkeypatch.setattr(strava_utils.core_cryptography, "decrypt_token_fernet", lambda value: value)


def _make_strava_fault(status_code: int) -> StravaFault:
    """Return a StravaFault whose .response.status_code equals *status_code*."""
    response = Mock()
    response.status_code = status_code
    response.headers = {}
    fault = StravaFault()
    fault.response = response
    return fault


# ---------------------------------------------------------------------------
# fetch_and_process_activity_streams — empty-stream (404) path
# ---------------------------------------------------------------------------


class TestFetchAndProcessActivityStreamsNotFound:
    """Tests for the 404 / no-streams path in fetch_and_process_activity_streams."""

    def _call(self, client: Mock, rate_limits) -> tuple:
        return activity_utils.fetch_and_process_activity_streams(
            strava_client=client,
            strava_activity_id=99,
            user_id=1,
            user_integrations=_integrations(),
            rate_limits=rate_limits,
        )

    def test_not_found_fault_returns_empty_streams(self, monkeypatch, rate_limits):
        """A StravaFault 404 yields thirteen empty/False return values."""
        client = Mock()
        client.get_activity_streams.side_effect = _make_strava_fault(404)

        monkeypatch.setattr(rate_limits, "is_rate_limited", lambda client_id: False)
        monkeypatch.setattr(activity_utils, "logger", Mock())

        result = self._call(client, rate_limits)

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

    def test_not_found_plain_exception_returns_empty_streams(self, monkeypatch, rate_limits):
        """stravalib's ObjectNotFound also yields empty stream data."""
        client = Mock()
        client.get_activity_streams.side_effect = ObjectNotFound()

        monkeypatch.setattr(rate_limits, "is_rate_limited", lambda client_id: False)
        monkeypatch.setattr(activity_utils, "logger", Mock())

        result = self._call(client, rate_limits)

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

    def test_rate_limit_fault_raises_429(self, monkeypatch, rate_limits):
        """A StravaFault 429 raises a domain error 429, not empty streams."""
        client = Mock()
        client.get_activity_streams.side_effect = _make_strava_fault(429)

        monkeypatch.setattr(rate_limits, "is_rate_limited", lambda client_id: False)
        monkeypatch.setattr(rate_limits, "mark_rate_limited", Mock())
        monkeypatch.setattr(activity_utils, "logger", Mock())

        with pytest.raises(core_exceptions.TooManyRequestsError):
            self._call(client, rate_limits)

    def test_pre_check_rate_limited_raises_429(self, monkeypatch, rate_limits):
        """When already rate-limited, raises a domain error 429 before any API call."""
        client = Mock()

        monkeypatch.setattr(rate_limits, "is_rate_limited", lambda client_id: True)
        monkeypatch.setattr(activity_utils, "logger", Mock())

        with pytest.raises(core_exceptions.TooManyRequestsError):
            self._call(client, rate_limits)

        client.get_activity_streams.assert_not_called()

    def test_a_limit_on_another_app_does_not_block_the_fetch(self, monkeypatch, rate_limits):
        client = Mock()
        client.get_activity_streams.side_effect = _make_strava_fault(404)
        rate_limits.mark_rate_limited("app-b", is_long_term=True)
        monkeypatch.setattr(activity_utils, "logger", Mock())

        self._call(client, rate_limits)

        client.get_activity_streams.assert_called_once()

    def test_a_limit_hit_here_is_recorded_against_this_app_only(self, monkeypatch, rate_limits):
        client = Mock()
        client.get_activity_streams.side_effect = _make_strava_fault(429)
        monkeypatch.setattr(activity_utils, "logger", Mock())

        with pytest.raises(core_exceptions.TooManyRequestsError):
            self._call(client, rate_limits)

        assert rate_limits.is_rate_limited("app-a") is True
        assert rate_limits.is_rate_limited("app-b") is False

    def test_unrelated_exception_raises_424(self, monkeypatch, rate_limits):
        """An unrelated exception raises a domain error 424."""
        client = Mock()
        client.get_activity_streams.side_effect = RuntimeError("network failure")

        monkeypatch.setattr(rate_limits, "is_rate_limited", lambda client_id: False)
        monkeypatch.setattr(activity_utils, "logger", Mock())

        with pytest.raises(core_exceptions.DependencyFailedError):
            self._call(client, rate_limits)


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
        monkeypatch.setattr(activity_utils.core_database, "SessionLocal", _TrackingSession)
        monkeypatch.setattr(
            activity_utils.activity_integration,
            "get_activity_by_strava_id",
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

        result = activity_utils.process_activity(Mock(id=555), 1, Mock(), "UTC", Mock(), Mock(), Mock())

        assert result.id == 7
        assert seen["during_parse"] == 0
        # The store gets its own short session.
        assert seen["during_save"] == 1

    def test_an_activity_already_stored_is_skipped_without_calling_strava(self, monkeypatch):
        seen = self._setup(monkeypatch, already_stored=True)

        assert activity_utils.process_activity(Mock(id=555), 1, Mock(), "UTC", Mock(), Mock(), Mock()) is None
        assert seen == {}


class TestFetchAndProcessActivityLapsRateLimit:
    """Laps count against the same per-app Strava quota as streams."""

    def _call(self, client: Mock, rate_limits):
        return activity_utils.fetch_and_process_activity_laps(client, 1, 1, [], _integrations(), rate_limits)

    def test_a_limited_app_raises_429_before_any_api_call(self, rate_limits):
        client = Mock()
        rate_limits.mark_rate_limited("app-a", is_long_term=True)

        with pytest.raises(core_exceptions.TooManyRequestsError):
            self._call(client, rate_limits)

        client.get_activity_laps.assert_not_called()

    def test_a_limit_on_another_app_does_not_block_the_fetch(self, rate_limits):
        client = Mock()
        client.get_activity_laps.return_value = []
        rate_limits.mark_rate_limited("app-b", is_long_term=True)

        assert self._call(client, rate_limits) == []

    def test_a_429_is_recorded_against_this_app_and_raised(self, rate_limits):
        client = Mock()
        client.get_activity_laps.side_effect = _make_strava_fault(429)

        with pytest.raises(core_exceptions.TooManyRequestsError):
            self._call(client, rate_limits)

        assert rate_limits.is_rate_limited("app-a") is True
        assert rate_limits.is_rate_limited("app-b") is False

    def test_not_found_returns_none(self, rate_limits):
        client = Mock()
        client.get_activity_laps.side_effect = _make_strava_fault(404)

        assert self._call(client, rate_limits) is None

    def test_another_failure_raises_so_the_activity_is_retried(self, rate_limits):
        client = Mock()
        client.get_activity_laps.side_effect = _make_strava_fault(503)

        with pytest.raises(core_exceptions.DependencyFailedError):
            self._call(client, rate_limits)

    def test_a_network_failure_raises_so_the_activity_is_retried(self, rate_limits):
        client = Mock()
        client.get_activity_laps.side_effect = RuntimeError("network failure")

        with pytest.raises(core_exceptions.DependencyFailedError):
            self._call(client, rate_limits)


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

    def _process(self, ele_stream: list[dict], rate_limits) -> dict:
        client = Mock()
        client.get_activity_laps.return_value = [self._lap()]
        laps = activity_utils.fetch_and_process_activity_laps(
            client, 1, 1, [(True, 4, ele_stream)], _integrations(), rate_limits
        )
        return laps[0]

    def test_invalid_altitude_stream_leaves_lap_elevation_none(self, rate_limits):
        """An altitude stream with no valid values yields None, not 0 m."""
        lap = self._process(rate_limits=rate_limits, ele_stream=[{"ele": None}, {"ele": None}, {"ele": None}])

        assert lap["total_ascent"] is None
        assert lap["total_descent"] is None

    def test_flat_altitude_stream_stores_zero(self, rate_limits):
        """A flat altitude stream yields a genuine 0 m ascent/descent."""
        lap = self._process(rate_limits=rate_limits, ele_stream=[{"ele": 100.0}, {"ele": 100.0}, {"ele": 100.0}])

        assert lap["total_ascent"] == 0
        assert lap["total_descent"] == 0


class TestStreamsConversion:
    """A stream is paired with the time stream; points without a timestamp are dropped."""

    def _call(self, streams: dict, rate_limits):
        client = Mock()
        client.get_activity_streams.return_value = {name: Mock(data=data) for name, data in streams.items()}
        return activity_utils.fetch_and_process_activity_streams(client, 99, 1, _integrations(), rate_limits)

    def test_a_stream_longer_than_time_is_cut_instead_of_failing(self, rate_limits, monkeypatch):
        monkeypatch.setattr(rate_limits, "is_rate_limited", lambda client_id: False)

        result = self._call({"time": [0, 1], "heartrate": [100, 110, 120]}, rate_limits)

        hr_waypoints, is_hr_set = result[4], result[5]
        assert hr_waypoints == [{"time": 0, "hr": 100}, {"time": 1, "hr": 110}]
        assert is_hr_set is True

    def test_pace_is_derived_from_velocity_with_zero_for_a_standstill(self, rate_limits, monkeypatch):
        monkeypatch.setattr(rate_limits, "is_rate_limited", lambda client_id: False)

        result = self._call({"time": [0, 1], "velocity_smooth": [0, 4]}, rate_limits)

        assert result[10] == [{"time": 0, "vel": 0}, {"time": 1, "vel": 4}]
        assert result[12] == [{"time": 0, "pace": 0}, {"time": 1, "pace": 0.25}]

    def test_missing_streams_are_reported_as_not_set(self, rate_limits, monkeypatch):
        monkeypatch.setattr(rate_limits, "is_rate_limited", lambda client_id: False)

        result = self._call({"time": [0, 1]}, rate_limits)

        assert [result[i] for i in (1, 3, 5, 7, 9, 11)] == [False] * 6


class TestFetchAndProcessActivitiesIsolation:
    """One activity that cannot be processed does not stop the rest of the window, and the window then fails."""

    def _run(self, monkeypatch, rate_limits, process):
        monkeypatch.setattr(rate_limits, "is_rate_limited", lambda client_id: False)
        monkeypatch.setattr(activity_utils, "logger", Mock())
        monkeypatch.setattr(activity_utils.core_database, "SessionLocal", lambda: MagicMock())
        monkeypatch.setattr(
            activity_utils.users_integration, "get_user", lambda *_a: Mock(id=1, timezone="Europe/Lisbon")
        )
        monkeypatch.setattr(
            activity_utils.users_privacy_settings_integration, "get_privacy_settings", lambda *_a: Mock()
        )
        monkeypatch.setattr(activity_utils, "process_activity", process)
        client = Mock()
        client.get_activities.return_value = [Mock(id=1), Mock(id=2), Mock(id=3)]
        return activity_utils.fetch_and_process_activities_by_dates(
            client, datetime(2026, 1, 1), datetime(2026, 1, 2), 1, _integrations(), rate_limits
        )

    def test_a_failing_activity_does_not_stop_the_others_but_fails_the_window(self, monkeypatch, rate_limits):
        processed = []

        def process(activity, *_args):
            processed.append(activity.id)
            if activity.id == 2:
                raise TypeError("calories is None")
            return f"stored-{activity.id}"

        with pytest.raises(TypeError, match="calories is None"):
            self._run(monkeypatch, rate_limits, process)

        assert processed == [1, 2, 3]

    def test_a_rate_limit_still_stops_the_window(self, monkeypatch, rate_limits):
        def process(activity, *_args):
            raise core_exceptions.TooManyRequestsError("slow down")

        with pytest.raises(core_exceptions.TooManyRequestsError):
            self._run(monkeypatch, rate_limits, process)

    def test_the_users_timezone_is_passed_down_once(self, monkeypatch, rate_limits):
        seen = []

        def process(activity, user_id, privacy, timezone, *_args):
            seen.append(timezone)

        self._run(monkeypatch, rate_limits, process)

        assert seen == ["Europe/Lisbon"] * 3


class TestARejectedTokenUnlinksTheAccount:
    """A Strava 401 anywhere in the activity sync hands the rejected token to ``handle_rejected_token``."""

    @pytest.fixture
    def handle(self, monkeypatch):
        handle = Mock()
        monkeypatch.setattr(strava_utils, "handle_rejected_token", handle)
        monkeypatch.setattr(activity_utils.core_database, "SessionLocal", MagicMock())
        monkeypatch.setattr(activity_utils.activity_integration, "get_activity_by_strava_id", lambda *a, **k: None)
        return handle

    def _integrations(self):
        return Mock(strava_client_id="app-a", strava_refresh_token="enc")

    def test_the_window_fetch(self, handle, rate_limits):
        client = Mock()
        client.get_activities.side_effect = AccessUnauthorized()

        with pytest.raises(core_exceptions.DependencyFailedError):
            activity_utils.fetch_and_process_activities_by_dates(
                client, datetime(2026, 1, 1), datetime(2026, 1, 2), 1, self._integrations(), rate_limits
            )

        assert handle.call_args.args[:2] == (1, "enc")

    def test_the_detail_fetch(self, handle, rate_limits):
        client = Mock()
        client.get_activity.side_effect = AccessUnauthorized()

        with pytest.raises(core_exceptions.DependencyFailedError):
            activity_utils.process_activity(Mock(id=9), 1, Mock(), "UTC", client, self._integrations(), rate_limits)

        assert handle.call_args.args[:2] == (1, "enc")

    def test_the_streams_fetch(self, handle, rate_limits):
        client = Mock()
        client.get_activity_streams.side_effect = AccessUnauthorized()

        with pytest.raises(core_exceptions.DependencyFailedError):
            activity_utils.fetch_and_process_activity_streams(
                strava_client=client,
                strava_activity_id=99,
                user_id=1,
                user_integrations=self._integrations(),
                rate_limits=rate_limits,
            )

        assert handle.call_args.args[:2] == (1, "enc")

    def test_the_laps_fetch(self, handle, rate_limits):
        client = Mock()
        client.get_activity_laps.side_effect = AccessUnauthorized()

        with pytest.raises(core_exceptions.DependencyFailedError):
            activity_utils.fetch_and_process_activity_laps(client, 99, 1, [], self._integrations(), rate_limits)

        assert handle.call_args.args[:2] == (1, "enc")

    def test_a_rejected_token_stops_the_window_instead_of_skipping_the_activity(self, handle, rate_limits, monkeypatch):
        calls = []

        def process(activity, *_args):
            calls.append(activity.id)
            strava_utils.raise_if_unauthorized(AccessUnauthorized(), 1, self._integrations())

        monkeypatch.setattr(activity_utils, "process_activity", process)
        monkeypatch.setattr(
            activity_utils.users_integration, "get_user", Mock(return_value=Mock(id=1, timezone="UTC", spec_set=None))
        )
        monkeypatch.setattr(activity_utils.users_privacy_settings_integration, "get_privacy_settings", Mock())
        monkeypatch.setattr(activity_utils.core_database, "SessionLocal", MagicMock())
        client = Mock()
        client.get_activities.return_value = [Mock(id=1), Mock(id=2)]

        with pytest.raises(strava_utils.StravaTokenRejectedError):
            activity_utils.fetch_and_process_activities_by_dates(
                client, datetime(2026, 1, 1), datetime(2026, 1, 2), 1, self._integrations(), rate_limits
            )

        assert calls == [1]
