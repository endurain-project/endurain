"""Tests that a FIT recording assembles into the right activities: totals, streams, laps and timezone."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import modules.activities.activity_file_import.assembly as assembly
import modules.activities.activity_file_import.recording as recording
from tests.activities.activity_file_import.assembled import assemble_recording, make_recording, session

_OWNER_TZ = "UTC"
_START = datetime(2026, 6, 20, 8, 20, 3, tzinfo=UTC)


def _summary(**overrides) -> recording.DeviceSummary:
    """Build a device summary of a 5006 s workout with the heart rate and calories the old fixture had."""
    values = {
        "total_elapsed_time": 5006.0,
        "total_timer_time": 5006.0,
        "avg_heart_rate": 145,
        "max_heart_rate": 177,
        "calories": 934,
    }
    values.update(overrides)
    return recording.DeviceSummary(**values)


def _rows(count: int, step: int = 10, **channels):
    """Build ``count`` sample rows ``step`` seconds apart; a channel given as a list is taken value by value."""
    return [
        {
            "time": _START + timedelta(seconds=i * step),
            **{key: (value[i] if isinstance(value, list) else value) for key, value in channels.items()},
        }
        for i in range(count)
    ]


def _assemble(rows=(), *, sport=None, summary=None, rec_fields=None, timezone=_OWNER_TZ, **session_fields):
    """Assemble one session and return its payload."""
    one = session(rows, sport=sport, summary=summary or _summary(), start_time=_START, **session_fields)
    (payload,) = assemble_recording(make_recording(one, **(rec_fields or {})), timezone=timezone)
    return payload


def _activity(*args, **kwargs):
    return _assemble(*args, **kwargs)["activity"]


class TestIdentity:
    def test_numeric_manufacturer_and_model_are_carried_as_strings(self):
        # The FIT decoder stringifies an unmapped numeric id (Amazfit/Zepp); the decoder tests cover it.
        activity = _activity(rec_fields={"manufacturer": "339", "product": "4567"})

        assert activity.tracker_manufacturer == "339"
        assert activity.tracker_model == "4567"

    def test_missing_manufacturer_and_model_stay_none(self):
        activity = _activity()

        assert activity.tracker_manufacturer is None
        assert activity.tracker_model is None


class TestHeartRate:
    def test_avg_and_max_are_recomputed_from_samples_without_zeros(self):
        # One sensor-off zero, then real readings; the device values included the zero.
        rows = _rows(3, heart_rate=[0, 150, 160])
        activity = _activity(rows, summary=_summary(avg_heart_rate=103, max_heart_rate=160))

        # Zeros excluded: mean([150, 160]) = 155, max = 160.
        assert activity.average_hr == 155
        assert activity.max_hr == 160

    def test_the_stream_keeps_the_zero(self):
        payload = _assemble(_rows(3, heart_rate=[0, 150, 160]))

        assert [w["hr"] for w in payload["hr_waypoints"]] == [0, 150, 160]

    def test_device_values_are_kept_without_samples(self):
        activity = _activity()

        assert activity.average_hr == 145
        assert activity.max_hr == 177


class TestSpeed:
    def test_avg_speed_falls_back_to_distance_over_timer(self):
        activity = _activity(summary=_summary(distance=10012.0, total_timer_time=5006.0))

        # 10012 m / 5006 s = 2.0 m/s.
        assert activity.average_speed == 2.0

    def test_device_speed_samples_give_the_max_when_the_session_has_a_distance(self):
        rows = _rows(2, speed=[2.0, 4.0])
        activity = _activity(rows, summary=_summary(distance=10012.0))

        assert activity.max_speed == 4.0

    def test_without_a_distance_speed_and_max_speed_stay_none(self):
        """Without distance there is no pace to invert, so the average and maximum are missing, not 0."""
        payload = _assemble(_rows(2, speed=[2.0, 4.0]))

        assert payload["activity"].average_speed is None
        assert payload["activity"].max_speed is None
        assert [w["vel"] for w in payload["vel_waypoints"]] == [2.0, 4.0]

    def test_a_device_speed_of_zero_on_a_session_without_distance_is_no_speed(self):
        """A strength or HIIT session's device writes an average speed of 0; nothing was covered, so there is none."""
        activity = _activity(summary=_summary(distance=0.0, avg_speed=0.0, max_speed=0.0))

        assert activity.average_speed is None
        assert activity.max_speed is None

    def test_device_speed_is_used_verbatim(self):
        activity = _activity(summary=_summary(distance=10012.0, avg_speed=2.5, max_speed=6.0))

        assert activity.average_speed == 2.5
        assert activity.max_speed == 6.0

    def test_no_speed_stream_without_positions_and_device_speed(self):
        payload = _assemble(_rows(3, heart_rate=140))

        assert payload["is_velocity_set"] is False
        assert payload["vel_waypoints"] == []
        assert payload["pace_waypoints"] == []


class TestCadence:
    def test_avg_and_max_fall_back_to_the_samples(self):
        activity = _activity(_rows(2, cadence=[80, 90]))

        # mean([80, 90]) = 85, max = 90.
        assert activity.average_cad == 85
        assert activity.max_cad == 90

    def test_device_cadence_is_used_verbatim(self):
        activity = _activity(_rows(2, cadence=[80, 90]), summary=_summary(avg_cadence=88, max_cadence=95))

        assert activity.average_cad == 88
        assert activity.max_cad == 95

    def test_running_cadence_is_doubled_across_the_activity_the_stream_and_the_laps(self):
        lap = recording.Lap(
            start_time=_START,
            total_elapsed_time=20.0,
            avg_cadence=84,
            max_cadence=88,
            avg_fractional_cadence=0.5,
            max_fractional_cadence=0.0,
        )
        payload = _assemble(
            _rows(2, cadence=[84, 90]),
            sport="running",
            summary=_summary(
                avg_cadence=85, max_cadence=93, avg_fractional_cadence=0.328125, max_fractional_cadence=0.0
            ),
            laps=(lap,),
        )

        # (85 + 0.328125) * 2 = 170.66 -> 171 ; (93 + 0) * 2 = 186.
        assert payload["activity"].average_cad == 171
        assert payload["activity"].max_cad == 186
        assert [wp["cad"] for wp in payload["cad_waypoints"]] == [168, 180]
        # (84 + 0.5) * 2 = 169 ; (88 + 0) * 2 = 176.
        assert payload["laps"][0]["avg_cadence"] == 169
        assert payload["laps"][0]["max_cadence"] == 176
        # The fraction is folded into avg/max_cadence above.
        assert payload["laps"][0]["avg_fractional_cadence"] is None
        assert payload["laps"][0]["max_fractional_cadence"] is None

    def test_running_zero_session_cadence_falls_back_to_the_samples(self):
        """A zero session cadence counts as missing, so the stream is used before doubling."""
        activity = _activity(
            _rows(2, cadence=[84, 90]), sport="running", summary=_summary(avg_cadence=0, max_cadence=0)
        )

        # mean([84, 90]) * 2 = 174 ; 90 * 2 = 180.
        assert activity.average_cad == 174
        assert activity.max_cad == 180

    def test_every_running_type_is_doubled_whatever_the_value(self):
        """FIT running cadence is per-leg by format, so every running type is doubled."""
        payload = _assemble(
            _rows(2, cadence=[128, None]), sport="treadmill", summary=_summary(avg_cadence=130, max_cadence=140)
        )

        assert payload["activity"].activity_type == "treadmill_run"
        assert payload["activity"].average_cad == 260
        assert payload["activity"].max_cad == 280
        # A sample with no cadence is not a stream point.
        assert [wp["cad"] for wp in payload["cad_waypoints"]] == [256]

    def test_running_max_without_avg_is_still_doubled(self):
        activity = _activity(sport="running", summary=_summary(max_cadence=93))

        assert activity.average_cad is None
        assert activity.max_cad == 186

    def test_stream_fallback_cadence_is_rounded_to_integers(self):
        activity = _activity(_rows(2, cadence=[80, 85]), sport="cycling")

        assert activity.average_cad == 82
        assert activity.max_cad == 85

    def test_cycling_cadence_is_stored_as_rpm(self):
        activity = _activity(sport="cycling", summary=_summary(avg_cadence=88, max_cadence=110))

        assert activity.average_cad == 88
        assert activity.max_cad == 110


class TestElevation:
    def test_gain_and_loss_fall_back_to_the_altitude_samples(self):
        # Climb 100 -> 200, then descend to 100, long enough for the wider smoothing windows to retain the trend.
        altitudes = list(range(100, 200, 2)) + list(range(200, 100, -2))
        activity = _activity(_rows(len(altitudes), altitude=altitudes))

        assert activity.elevation_gain is not None
        assert activity.elevation_gain > 0
        assert activity.elevation_loss is not None
        assert activity.elevation_loss > 0

    def test_device_gain_and_loss_are_used_verbatim(self):
        activity = _activity(_rows(2, altitude=[100, 130]), summary=_summary(total_ascent=250, total_descent=240))

        assert activity.elevation_gain == 250
        assert activity.elevation_loss == 240

    def test_a_computed_zero_on_a_flat_ride_is_stored_as_zero(self):
        activity = _activity(_rows(6, altitude=100.0))

        assert activity.elevation_gain == 0
        assert activity.elevation_loss == 0

    def test_an_altitude_stream_with_no_values_leaves_session_and_lap_elevation_none(self):
        lap = recording.Lap(start_time=_START, total_elapsed_time=50.0)
        payload = _assemble(_rows(6, heart_rate=140), laps=(lap,))

        assert payload["activity"].elevation_gain is None
        assert payload["activity"].elevation_loss is None
        assert payload["is_elevation_set"] is False
        assert payload["laps"][0]["total_ascent"] is None
        assert payload["laps"][0]["total_descent"] is None


class TestDistance:
    def test_no_distance_data_leaves_distance_zero_and_pace_and_speeds_none(self):
        activity = _activity()

        assert activity.distance == 0
        assert activity.pace is None
        assert activity.average_speed is None
        assert activity.max_speed is None

    def test_missing_distance_falls_back_to_avg_speed_times_timer(self):
        activity = _activity(summary=_summary(avg_speed=1.495, total_timer_time=1890.0))

        assert activity.distance == round(1.495 * 1890.0)
        assert activity.pace > 0

    def test_missing_distance_falls_back_to_the_geodesic_length_of_the_track(self):
        # ~0.01 deg of latitude is about 1.1 km.
        lat = [40.0 + 0.002 * i for i in range(6)]
        activity = _activity(_rows(6, lat=lat, lon=-3.0))

        assert 1000 < activity.distance < 1200
        assert activity.pace > 0

    def test_the_session_distance_takes_precedence_over_the_fallbacks(self):
        activity = _activity(
            _rows(3, distance=[0.0, 100.0, 200.0]),
            summary=_summary(distance=5000.0, avg_speed=1.495, total_timer_time=1890.0),
        )

        assert activity.distance == 5000

    def test_the_last_distance_sample_comes_before_the_laps_and_the_track(self):
        lap = recording.Lap(start_time=_START, total_elapsed_time=20.0, total_distance=999.0)
        activity = _activity(_rows(3, distance=[0.0, 100.0, 200.0]), laps=(lap,))

        assert activity.distance == 200

    def test_the_sum_of_the_laps_comes_before_the_track(self):
        laps = (
            recording.Lap(start_time=_START, total_elapsed_time=20.0, total_distance=300.0),
            recording.Lap(start_time=_START + timedelta(seconds=20), total_elapsed_time=20.0, total_distance=400.0),
        )
        lat = [40.0 + 0.002 * i for i in range(6)]
        activity = _activity(_rows(6, lat=lat, lon=-3.0), laps=laps)

        assert activity.distance == 700


class TestLapElevation:
    def test_missing_lap_ascent_and_descent_are_computed_from_the_altitude_stream(self):
        # 1 Hz: 60 s climbing 1 m/s, then 60 s descending, long enough for the smoothing windows.
        altitudes = [100 + min(i, 120 - i) for i in range(121)]
        lap = recording.Lap(start_time=_START, total_elapsed_time=120.0)

        payload = _assemble(_rows(121, step=1, altitude=altitudes), laps=(lap,))

        assert payload["laps"][0]["total_ascent"] is not None
        assert payload["laps"][0]["total_ascent"] > 0
        assert payload["laps"][0]["total_descent"] is not None
        assert payload["laps"][0]["total_descent"] > 0

    def test_a_device_lap_ascent_wins_and_only_the_missing_field_is_filled(self):
        lap = recording.Lap(start_time=_START, total_elapsed_time=40.0, total_ascent=250)

        payload = _assemble(_rows(5, altitude=[100, 110, 120, 110, 100]), laps=(lap,))

        assert payload["laps"][0]["total_ascent"] == 250
        assert payload["laps"][0]["total_descent"] is not None

    def test_lap_elevation_stays_none_without_an_altitude_stream(self):
        lap = recording.Lap(start_time=_START, total_elapsed_time=80.0)

        payload = _assemble(laps=(lap,))

        assert payload["laps"][0]["total_ascent"] is None
        assert payload["laps"][0]["total_descent"] is None

    def test_a_flat_lap_stores_zero(self):
        lap = recording.Lap(start_time=_START, total_elapsed_time=50.0)

        payload = _assemble(_rows(6, altitude=100.0), laps=(lap,))

        assert payload["laps"][0]["total_ascent"] == 0
        assert payload["laps"][0]["total_descent"] == 0


class TestLapSpeed:
    """A device lap's speed and pace: the device's speed, else distance over timer; a speed of 0 is missing."""

    @staticmethod
    def _lap(**fields):
        lap = recording.Lap(start_time=_START, total_elapsed_time=300.0, **fields)
        return _assemble(laps=(lap,))["laps"][0]

    def test_the_device_speed_gives_the_pace_as_its_reciprocal(self):
        lap = self._lap(avg_speed=4.0, max_speed=5.0)

        assert lap["enhanced_avg_speed"] == 4.0
        assert lap["enhanced_avg_pace"] == 1 / 4.0
        assert lap["enhanced_max_pace"] == 1 / 5.0

    def test_the_average_falls_back_to_distance_over_timer(self):
        lap = self._lap(total_distance=1000, total_timer_time=250)

        assert lap["enhanced_avg_speed"] == 4.0
        assert lap["enhanced_avg_pace"] == 1 / 4.0

    def test_no_speed_and_no_usable_distance_leaves_pace_unset(self):
        lap = self._lap(total_distance=0, total_timer_time=0)

        assert lap["enhanced_avg_speed"] is None
        assert lap["enhanced_avg_pace"] is None

    def test_a_speed_of_zero_is_stored_as_none(self):
        lap = self._lap(avg_speed=0.0, max_speed=0.0)

        assert lap["enhanced_avg_speed"] is None
        assert lap["enhanced_max_speed"] is None
        assert lap["enhanced_avg_pace"] is None
        assert lap["enhanced_max_pace"] is None


class TestLapSwimPace:
    """Active time and pace of a pool swim from its split summaries and lengths."""

    @staticmethod
    def _swim(**fields):
        return _activity(sport="lap_swimming", summary=_summary(distance=100.0, total_timer_time=50.0), **fields)

    def test_a_split_summary_without_timer_time_adds_no_active_time(self):
        """A split summary that carries no timer time counts no seconds instead of failing the whole file."""
        activity = self._swim(
            split_summaries=(
                recording.SplitSummary(split_type="interval_active", total_timer_time=None),
                recording.SplitSummary(split_type="interval_active", total_timer_time=40.0),
            )
        )

        assert activity.total_timer_time == 40.0
        assert activity.pace == 0.4

    def test_a_rest_split_summary_adds_no_active_time(self):
        """fitdecode names a rest split ``interval_rest``; its seconds are rest, not working time."""
        activity = self._swim(
            split_summaries=(
                recording.SplitSummary(split_type="interval_active", total_timer_time=40.0),
                recording.SplitSummary(split_type="interval_rest", total_timer_time=10.0),
            )
        )

        assert activity.total_timer_time == 40.0
        assert activity.pace == 0.4

    def test_only_active_lengths_with_timer_time_count(self):
        activity = self._swim(
            lengths=(
                recording.Length(length_type="active", total_timer_time=25.0),
                recording.Length(length_type="active", total_timer_time=None),
                recording.Length(length_type="idle", total_timer_time=10.0),
                recording.Length(length_type="active", total_timer_time=15.0),
            )
        )

        assert activity.total_timer_time == 40.0
        assert activity.pace == 0.4


class TestFindTimezoneName:
    """A bare UTC offset does not identify a zone, so the answer must be honest.

    Scanning every known zone and returning the first match was a lottery (``+00:00`` could yield
    ``Africa/Abidjan``) and the winning name carried that zone's DST rules for every other date of the year.
    """

    _REF = datetime(2026, 6, 20, 8, 20, 3, tzinfo=UTC)

    def test_whole_hour_offset_maps_to_a_fixed_offset_zone(self):
        # POSIX sign inversion: Etc/GMT-9 is UTC+9.
        assert assembly._find_timezone_name(9 * 3600, self._REF) == "Etc/GMT-9"
        assert assembly._find_timezone_name(-5 * 3600, self._REF) == "Etc/GMT+5"

    def test_zero_offset_is_utc(self):
        assert assembly._find_timezone_name(0, self._REF) == "UTC"

    def test_result_is_deterministic(self):
        first = assembly._find_timezone_name(2 * 3600, self._REF)
        second = assembly._find_timezone_name(2 * 3600, self._REF)
        assert first == second

    def test_resolved_zone_reproduces_the_offset(self):
        name = assembly._find_timezone_name(9 * 3600, self._REF)
        assert self._REF.astimezone(ZoneInfo(name)).utcoffset().total_seconds() == 9 * 3600

    def test_half_hour_offset_falls_back_to_a_named_zone(self):
        # India (+05:30) has no Etc/GMT equivalent.
        name = assembly._find_timezone_name(5 * 3600 + 1800, self._REF)
        assert name is not None
        assert self._REF.astimezone(ZoneInfo(name)).utcoffset().total_seconds() == 5 * 3600 + 1800

    def test_impossible_offset_returns_none(self):
        assert assembly._find_timezone_name(1234, self._REF) is None


class TestPerSessionTimezone:
    """Each session of a multi-activity file resolves its own timezone."""

    def test_a_session_without_positions_does_not_inherit_the_previous_ones_zone(self):
        positioned = session(
            _rows(2, lat=[35.68, 35.69], lon=139.69), sport="running", start_time=_START, summary=_summary()
        )
        indoor = session(
            _rows(2, heart_rate=140), sport="running", start_time=_START + timedelta(hours=2), summary=_summary()
        )

        first, second = assemble_recording(make_recording(positioned, indoor), timezone="Europe/Madrid")

        assert first["activity"].timezone == "Asia/Tokyo"
        assert second["activity"].timezone == "Europe/Madrid"

    def test_an_unresolvable_offset_keeps_the_default(self):
        activity = _activity(rec_fields={"local_time_offset": 1234}, timezone="Europe/Madrid")

        assert activity.timezone == "Europe/Madrid"

    def test_a_virtual_activity_keeps_the_default_whatever_the_file_says(self):
        activity = _activity(
            _rows(2, lat=[35.68, 35.69], lon=139.69),
            sport="cycling",
            rec_fields={"local_time_offset": 9 * 3600},
            timezone="Europe/Madrid",
            summary=_summary(),
        )
        virtual = _activity(
            _rows(2, lat=[35.68, 35.69], lon=139.69),
            sport="virtual_ride",
            rec_fields={"local_time_offset": 9 * 3600},
            timezone="Europe/Madrid",
        )

        assert activity.timezone == "Asia/Tokyo"
        assert virtual.timezone == "Europe/Madrid"


class TestOwnerTimezoneFallback:
    """A GPS-less session falls back to the athlete's timezone, not the server's.

    Indoor rides, treadmill runs and pool swims carry no GPS track, so there is nothing in the file to resolve a zone
    from. Defaulting to the server's TZ stamped a US athlete's treadmill run with the host's European timezone, which
    then drove both its displayed start time and which day it was summarised into.
    """

    def test_uses_the_owner_timezone_when_the_session_has_no_gps(self):
        assert _activity(timezone="America/Los_Angeles").timezone == "America/Los_Angeles"

    def test_the_files_own_offset_still_wins_over_the_owner_timezone(self):
        """What the device recorded beats a profile default."""
        activity = _activity(rec_fields={"device_time_offset": 9 * 3600}, timezone="America/Los_Angeles")

        assert activity.timezone == "Etc/GMT-9"


class TestOffsetVersusAthleteTimezone:
    """A reported UTC offset is evidence of *where*, not of *which zone*.

    Turning it straight into a fixed-offset ``Etc/GMT+-H`` name is DST-free, so the same athlete's indoor rides would
    be stamped differently in winter and summer. When the offset agrees with their configured zone, that zone is the
    stable, DST-correct name for the same instant.
    """

    @staticmethod
    def _zone(offset_seconds: int, when: datetime, default: str) -> str:
        one = session(_rows(1), sport="running", start_time=when, summary=_summary())
        rec = make_recording(one, device_time_offset=offset_seconds)
        (payload,) = assemble_recording(rec, timezone=default)
        return payload["activity"].timezone

    def test_prefers_the_athlete_zone_when_the_offset_agrees(self):
        # Los Angeles is UTC-8 in January.
        zone = self._zone(-8 * 3600, datetime(2024, 1, 15, 17, 0, tzinfo=UTC), "America/Los_Angeles")

        assert zone == "America/Los_Angeles"

    def test_the_same_athlete_gets_the_same_zone_across_dst(self):
        """The whole point: winter and summer indoor rides agree."""
        winter = self._zone(-8 * 3600, datetime(2024, 1, 15, 17, 0, tzinfo=UTC), "America/Los_Angeles")
        # Los Angeles is UTC-7 in July, so the device reports a different offset.
        summer = self._zone(-7 * 3600, datetime(2024, 7, 15, 16, 0, tzinfo=UTC), "America/Los_Angeles")

        assert [winter, summer] == ["America/Los_Angeles", "America/Los_Angeles"]

    def test_falls_back_to_a_fixed_offset_when_the_athlete_was_travelling(self):
        """A mismatch means they were not at home; trust the device."""
        zone = self._zone(9 * 3600, datetime(2024, 1, 15, 0, 0, tzinfo=UTC), "America/Los_Angeles")

        assert zone == "Etc/GMT-9"

    def test_an_unusable_athlete_zone_does_not_break_resolution(self):
        zone = self._zone(9 * 3600, datetime(2024, 1, 15, 0, 0, tzinfo=UTC), "Not/AZone")

        assert zone == "Etc/GMT-9"


class TestActivityLocalTimestampOffset:
    """A GPS-less session resolves its timezone from the FIT activity message offset."""

    @staticmethod
    def _zone(local, device, default=_OWNER_TZ):
        return _activity(
            rec_fields={"local_time_offset": local, "device_time_offset": device}, timezone=default
        ).timezone

    def test_resolves_timezone_from_activity_offset(self):
        assert self._zone(2 * 3600, None) == "Etc/GMT-2"

    def test_activity_offset_takes_precedence_over_device_settings(self):
        assert self._zone(2 * 3600, 3600) == "Etc/GMT-2"

    def test_zero_activity_offset_resolves_to_utc_without_device_settings(self):
        assert self._zone(0, 0) == "UTC"

    def test_zero_activity_offset_yields_to_nonzero_device_settings(self):
        assert self._zone(0, 3600) == "Etc/GMT-1"

    def test_falls_back_to_device_settings_without_activity_offset(self):
        assert self._zone(None, 3600) == "Etc/GMT-1"

    def test_prefers_the_athlete_zone_when_the_activity_offset_agrees(self):
        # Paris is UTC+2 in June.
        assert self._zone(2 * 3600, None, "Europe/Paris") == "Europe/Paris"

    def test_gps_track_takes_precedence_over_activity_offset(self):
        activity = _activity(
            _rows(2, lat=[35.68, 35.69], lon=139.69), rec_fields={"local_time_offset": 2 * 3600}, summary=_summary()
        )

        assert activity.timezone == "Asia/Tokyo"


class TestName:
    """The activity name: the caller's, else the file's workout name, else the default."""

    def test_the_caller_name_wins_then_the_workout_name_then_the_default(self):
        one = session(_rows(2), summary=_summary(), start_time=_START)

        (named,) = assemble_recording(make_recording(one, name="Base"), name="Mine")
        (from_file,) = assemble_recording(make_recording(one, name="Base"))
        (default,) = assemble_recording(make_recording(one))

        assert named["activity"].name == "Mine"
        assert from_file["activity"].name == "Base"
        assert default["activity"].name == "Workout"
