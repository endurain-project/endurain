"""Tests that FIT bytes decode and assemble end to end: message layouts, encodings, summaries and damaged files."""

import struct
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_file_import.assembly as assembly
import modules.activities.activity_file_import.fit_decoder as fit_decoder
import modules.activities.activity_file_import.parser_registry as registry
import modules.activities.activity_file_import.recording as recording
from tests._helpers.auth import MOCK_USER_ID
from tests.activities.activity_file_import import assembled, fit_files
from tests.activities.activity_file_import.fit_files import RawField

_T0 = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)

_ENUM = 0x00
_SINT8 = 0x01
_UINT8 = 0x02
_SINT16 = 0x83
_UINT16 = 0x84
_SINT32 = 0x85
_UINT32 = 0x86
_STRING = 0x07
_BYTE = 0x0D

# Global message numbers.
_SESSION = 18
_LAP = 19
_RECORD = 20
_DEVICE_SETTINGS = 2
_WORKOUT_STEP = 27
_MONITORING = 55
_LENGTH = 101
_SET = 225
_SPLIT = 312
_SPLIT_SUMMARY = 313
_MONITORING_HR_DATA = 211
_FIELD_DESCRIPTION = 206
_DEVELOPER_DATA_ID = 207

# Sports and sub sports.
_SPORT_CYCLING = 2
_SPORT_SWIMMING = 5
_SPORT_PADEL = 64
_SUB_SPORT_VIRTUAL_ACTIVITY = 58
_SUB_SPORT_LAP_SWIMMING = 17
_SUB_SPORT_PADEL = 85


def _fit_time(moment: datetime) -> int:
    return int((moment - fit_files._FIT_EPOCH).total_seconds())


def _semicircles(degrees: float) -> int:
    return round(degrees * 2**31 / 180)


def _at(second: int) -> datetime:
    return _T0 + timedelta(seconds=second)


def _record(second: int, *fields: RawField, local_type: int = 2) -> bytes:
    """A record ``second`` seconds after the start, carrying its own definition."""
    return fit_files.raw_message(_RECORD, [(253, _UINT32, _fit_time(_at(second))), *fields], local_type=local_type)


def _lap(start_second: int, elapsed: int, *fields: RawField) -> bytes:
    return fit_files.raw_message(
        _LAP,
        [
            (253, _UINT32, _fit_time(_at(start_second + elapsed))),
            (2, _UINT32, _fit_time(_at(start_second))),
            (7, _UINT32, elapsed * 1000),
            (8, _UINT32, elapsed * 1000),
            *fields,
        ],
        local_type=1,
    )


def _session(elapsed: int = 40, *fields: RawField) -> bytes:
    """A session starting at ``_T0`` that lasts ``elapsed`` seconds (elapsed and timer time alike)."""
    return fit_files.raw_message(
        _SESSION,
        [
            (253, _UINT32, _fit_time(_at(elapsed))),
            (2, _UINT32, _fit_time(_T0)),
            (7, _UINT32, elapsed * 1000),
            (8, _UINT32, elapsed * 1000),
            *fields,
        ],
        local_type=3,
    )


def _write(tmp_path: Path, content: bytes) -> str:
    path = tmp_path / "activity.fit"
    path.write_bytes(content)
    return str(path)


def _decode(tmp_path: Path, *messages: bytes) -> recording.Recording:
    return fit_decoder.decode_fit(_write(tmp_path, fit_files.fit_file(*messages)))


def _assemble(tmp_path: Path, *messages: bytes, timezone: str = "UTC") -> list[assembly.ActivityFilePayload]:
    return assembled.assemble_fit(_write(tmp_path, fit_files.fit_file(*messages)), timezone=timezone)


def _payload(tmp_path: Path, *messages: bytes, timezone: str = "UTC") -> assembly.ActivityFilePayload:
    [payload] = _assemble(tmp_path, *messages, timezone=timezone)
    return payload


def _import(tmp_path: Path, *messages: bytes, timezone: str = "UTC"):
    path = _write(tmp_path, fit_files.fit_file(*messages))
    parser = registry.get_parser(".fit")
    assert parser is not None
    return parser(path, MOCK_USER_ID, None, timezone, 1.0)


class TestSplitMessages:
    """The decoder never reads the FIT ``split`` message; the split summary only feeds the swim active time."""

    def test_a_file_with_split_messages_assembles_to_the_same_activity_as_without(self, tmp_path):
        split = fit_files.raw_message(
            _SPLIT,
            [
                (0, _ENUM, 3),
                (1, _UINT32, 65_000),
                (2, _UINT32, 60_000),
                (3, _UINT32, 25_000),
                (4, _UINT32, 3_500),
                (9, _UINT32, _fit_time(_T0)),
                (13, _UINT16, 12),
                (14, _UINT16, 7),
                (21, _SINT32, _semicircles(40)),
                (22, _SINT32, _semicircles(-3)),
                (23, _SINT32, _semicircles(41)),
                (24, _SINT32, _semicircles(-4)),
                (25, _UINT32, 5_000),
                (27, _UINT32, _fit_time(_at(65))),
                (28, _UINT32, 9),
                (74, _UINT32, (100 + 500) * 5),
            ],
            local_type=1,
        )
        bare_split = fit_files.raw_message(_SPLIT, [(0, _ENUM, 4)], local_type=1)
        record = _record(0, (3, _UINT8, 140))

        with_splits = (record, split, bare_split, _session())
        without = (record, _session())

        assert _decode(tmp_path, *with_splits) == _decode(tmp_path, *without)
        assert _assemble(tmp_path, *with_splits) == _assemble(tmp_path, *without)

    def test_a_split_summary_carries_its_type_and_working_seconds(self, tmp_path):
        summary = fit_files.raw_message(_SPLIT_SUMMARY, [(0, _ENUM, 3), (4, _UINT32, 90_500)])

        (session,) = _decode(tmp_path, summary, _session()).sessions

        assert session.split_summaries == (recording.SplitSummary(split_type="interval_active", total_timer_time=90.5),)

    def test_a_split_summary_without_a_type_or_time_leaves_both_unset(self, tmp_path):
        summary = fit_files.raw_message(_SPLIT_SUMMARY, [(3, _UINT16, 4)])

        (session,) = _decode(tmp_path, summary, _session()).sessions

        assert session.split_summaries == (recording.SplitSummary(split_type=None, total_timer_time=None),)

    def test_a_split_summary_with_an_invalid_time_leaves_it_unset(self, tmp_path):
        summary = fit_files.raw_message(_SPLIT_SUMMARY, [(0, _ENUM, 4), (4, _UINT32, None)])

        (session,) = _decode(tmp_path, summary, _session()).sessions

        assert session.split_summaries == (recording.SplitSummary(split_type="interval_rest", total_timer_time=None),)

    def test_a_split_summary_belongs_to_the_session_message_that_follows_it(self, tmp_path):
        summary = fit_files.raw_message(_SPLIT_SUMMARY, [(0, _ENUM, 3), (4, _UINT32, 90_500)])
        later = fit_files.raw_message(
            _SESSION,
            [(253, _UINT32, _fit_time(_at(3620))), (2, _UINT32, _fit_time(_at(3600))), (7, _UINT32, 20_000)],
            local_type=3,
        )

        first, second = _decode(tmp_path, _session(), summary, later).sessions

        assert first.split_summaries == ()
        assert [item.total_timer_time for item in second.split_summaries] == [90.5]


class TestSetMessages:
    def test_a_set_is_decoded_with_its_raw_category(self, tmp_path):
        exercise_set = fit_files.raw_message(
            _SET,
            [
                (0, _UINT32, 30_000),
                (3, _UINT16, 10),
                (4, _UINT16, 16 * 20),
                (5, _ENUM, 1),
                (6, _UINT32, _fit_time(_T0)),
                (7, _UINT16, 28),
                (8, _UINT16, 3),
            ],
        )

        [decoded] = _payload(tmp_path, exercise_set, _session())["sets"]

        # Duration in seconds, repetitions, weight in kg, set type, start, raw category and sub category.
        assert decoded == [30.0, 10, 20.0, "active", _T0, 28, 3]

    def test_a_rest_set_has_no_category(self, tmp_path):
        rest = fit_files.raw_message(_SET, [(0, _UINT32, 30_000), (5, _ENUM, 0)])

        [decoded] = _payload(tmp_path, rest, _session())["sets"]

        assert decoded == [30.0, None, None, "rest", None, None, None]

    def test_a_set_with_a_sub_category_but_no_category_takes_category_zero(self, tmp_path):
        exercise_set = fit_files.raw_message(_SET, [(0, _UINT32, 30_000), (8, _UINT16, 3)])

        [decoded] = _payload(tmp_path, exercise_set, _session())["sets"]

        assert decoded == [30.0, None, None, None, None, 0, 3]

    def test_a_set_with_category_zero_keeps_it(self, tmp_path):
        exercise_set = fit_files.raw_message(_SET, [(7, _UINT16, 0), (8, _UINT16, 1)])

        [decoded] = _payload(tmp_path, exercise_set, _session())["sets"]

        assert decoded[5:] == [0, 1]

    def test_a_session_without_sets_has_no_sets_key(self, tmp_path):
        assert "sets" not in _payload(tmp_path, _session())


class TestWorkoutStepMessages:
    @staticmethod
    def _step(*fields: RawField) -> bytes:
        # A step always names its duration type; the stored step requires it.
        return fit_files.raw_message(_WORKOUT_STEP, [(1, _ENUM, 0), *fields])

    def _decoded(self, tmp_path: Path, step: bytes):
        [decoded] = _payload(tmp_path, step, _session())["workout_steps"]
        return decoded

    def test_a_step_is_decoded_with_its_targets_and_exercise(self, tmp_path):
        step = self._step(
            (254, _UINT16, 2),
            (2, _UINT32, 600_000),
            (3, _ENUM, 1),
            (4, _UINT32, 100),
            (7, _ENUM, 0),
            (8, _STRING, "keep steady"),
            (10, _UINT16, 5),
            (11, _UINT16, 0),
            (12, _UINT16, 2_500),
            (13, _ENUM, 1),
        )

        decoded = self._decoded(tmp_path, step)

        assert decoded.model_dump() == {
            "message_index": 2,
            "duration_type": "time",
            "duration_value": 600.0,
            "target_type": "heart_rate",
            "target_value": 100,
            "intensity": "active",
            "notes": "keep steady",
            "exercise_category": 5,
            "exercise_name": 0,
            "exercise_weight": 25.0,
            "weight_display_unit": "kilogram",
            "secondary_target_value": None,
        }

    def test_a_swim_stroke_target_moves_its_stroke_to_the_secondary_target(self, tmp_path):
        decoded = self._decoded(tmp_path, self._step((3, _ENUM, 11), (4, _UINT32, 2), (7, _ENUM, 1)))

        assert (decoded.target_type, decoded.target_value, decoded.secondary_target_value) == (
            "swim_stroke",
            None,
            "breaststroke",
        )
        assert decoded.intensity == "rest"

    def test_the_any_stroke_value_of_a_swim_target_becomes_any_stroke(self, tmp_path):
        decoded = self._decoded(tmp_path, self._step((3, _ENUM, 11), (4, _UINT32, 255)))

        assert (decoded.target_value, decoded.secondary_target_value) == (None, "any stroke")

    def test_a_swim_target_with_an_unnamed_stroke_keeps_its_number(self, tmp_path):
        decoded = self._decoded(tmp_path, self._step((3, _ENUM, 11), (4, _UINT32, 9)))

        assert (decoded.target_value, decoded.secondary_target_value) == (9, None)

    def test_a_target_value_of_255_on_another_target_is_kept(self, tmp_path):
        decoded = self._decoded(tmp_path, self._step((3, _ENUM, 13), (4, _UINT32, 255)))

        assert (decoded.target_type, decoded.target_value, decoded.secondary_target_value) == (
            "heart_rate_lap",
            255,
            None,
        )

    def test_the_raw_intensity_seven_reads_as_active(self, tmp_path):
        assert self._decoded(tmp_path, self._step((7, _ENUM, 7))).intensity == "active"

    def test_an_exercise_name_without_a_category_takes_category_zero(self, tmp_path):
        decoded = self._decoded(tmp_path, self._step((11, _UINT16, 4)))

        assert (decoded.exercise_category, decoded.exercise_name) == (0, 4)

    def test_a_step_without_exercise_fields_leaves_them_unset(self, tmp_path):
        decoded = self._decoded(tmp_path, self._step())

        assert (decoded.exercise_category, decoded.exercise_name) == (None, None)

    def test_a_step_without_a_duration_type_is_kept_without_one(self, tmp_path):
        decoded = self._decoded(tmp_path, fit_files.raw_message(_WORKOUT_STEP, [(3, _ENUM, 1)]))

        assert (decoded.duration_type, decoded.target_type) == (None, "heart_rate")


class TestMonitoringMessages:
    def test_monitoring_messages_do_not_change_what_the_file_reads(self, tmp_path):
        """Daily wellness samples (steps, heart rate, resting heart rate) are not activity data and are not read."""
        step = fit_files.raw_message(_WORKOUT_STEP, [(1, _ENUM, 0)])
        monitoring = fit_files.raw_message(
            _MONITORING, [(253, _UINT32, _fit_time(_T0)), (3, _UINT32, 40), (27, _UINT8, 62)], local_type=1
        )
        resting = fit_files.raw_message(
            _MONITORING_HR_DATA, [(253, _UINT32, _fit_time(_T0)), (0, _UINT8, 48), (1, _UINT8, 50)], local_type=2
        )

        with_monitoring = (step, monitoring, resting, _session())

        assert _decode(tmp_path, *with_monitoring) == _decode(tmp_path, step, _session())
        assert _assemble(tmp_path, *with_monitoring) == _assemble(tmp_path, step, _session())


class TestDeviceSettingsOffset:
    @staticmethod
    def _settings(offset: int | None) -> bytes:
        return fit_files.raw_message(_DEVICE_SETTINGS, [(2, _UINT32, offset)])

    def test_a_positive_offset_is_read_as_is(self, tmp_path):
        assert _decode(tmp_path, self._settings(3600)).device_time_offset == 3600

    def test_an_offset_written_as_an_unsigned_number_is_read_as_negative(self, tmp_path):
        assert _decode(tmp_path, self._settings(2**32 - 3600)).device_time_offset == -3600

    def test_an_invalid_offset_reads_as_none(self, tmp_path):
        assert _decode(tmp_path, self._settings(None)).device_time_offset is None

    def test_a_negative_offset_names_a_fixed_offset_zone_for_a_session_without_gps(self, tmp_path):
        activity = _payload(tmp_path, self._settings(2**32 - 5 * 3600), _session(), timezone="Europe/Paris")["activity"]

        assert activity.timezone == "Etc/GMT+5"

    def test_an_offset_beyond_every_real_zone_keeps_the_default_timezone(self, tmp_path):
        activity = _payload(tmp_path, self._settings(15 * 3600), _session(), timezone="Europe/Paris")["activity"]

        assert activity.timezone == "Europe/Paris"

    def test_a_half_hour_offset_names_a_zone_with_that_offset(self, tmp_path):
        activity = _payload(tmp_path, self._settings(19_800), _session(), timezone="Europe/Paris")["activity"]

        assert activity.start_time.astimezone(ZoneInfo(activity.timezone)).utcoffset() == timedelta(seconds=19_800)


class TestTimezoneName:
    @pytest.mark.parametrize(("hours", "zone"), [(9, "Etc/GMT-9"), (14, "Etc/GMT-14")])
    def test_a_whole_hour_offset_in_range_maps_to_its_fixed_offset_zone(self, tmp_path, hours, zone):
        settings = fit_files.raw_message(_DEVICE_SETTINGS, [(2, _UINT32, hours * 3600)])

        assert _payload(tmp_path, settings, _session())["activity"].timezone == zone

    def test_a_whole_hour_offset_past_every_zone_names_none(self, tmp_path):
        settings = fit_files.raw_message(_DEVICE_SETTINGS, [(2, _UINT32, 15 * 3600)])

        assert _payload(tmp_path, settings, _session(), timezone="Europe/Paris")["activity"].timezone == "Europe/Paris"


class TestPoolSwimming:
    @staticmethod
    def _length(index: int, length_type: int, seconds: int, *, timed: bool = True) -> bytes:
        return fit_files.raw_message(
            _LENGTH,
            [
                (254, _UINT16, index),
                (2, _UINT32, _fit_time(_at(30 * index))),
                (3, _UINT32, seconds * 1000),
                *([(4, _UINT32, seconds * 1000)] if timed else []),
                (5, _UINT16, 18),
                (6, _UINT16, 1_200),
                (7, _ENUM, 2),
                (9, _UINT8, 30),
                (12, _ENUM, length_type),
            ],
            local_type=1,
        )

    @staticmethod
    def _swim_session(elapsed: int) -> bytes:
        return _session(
            elapsed,
            (5, _ENUM, _SPORT_SWIMMING),
            (6, _ENUM, _SUB_SPORT_LAP_SWIMMING),
            (9, _UINT32, 5_000),
        )

    def test_a_length_is_decoded(self, tmp_path):
        (session,) = _decode(tmp_path, self._length(0, 1, 28), _session()).sessions

        assert session.lengths == (
            recording.Length(
                message_index=0,
                start_time=_T0,
                total_elapsed_time=28.0,
                total_timer_time=28.0,
                total_strokes=18,
                avg_speed=1.2,
                swim_stroke="breaststroke",
                avg_swimming_cadence=30,
                length_type="active",
            ),
        )

    def test_the_active_time_and_pace_count_only_the_active_lengths(self, tmp_path):
        activity = _payload(
            tmp_path,
            self._length(0, 1, 28),
            self._length(1, 0, 10),
            self._length(2, 1, 30),
            self._swim_session(60),
        )["activity"]

        assert activity.activity_type.name == "LAP_SWIMMING"
        assert activity.distance == 50
        assert activity.total_timer_time == 58
        assert activity.pace == pytest.approx(58 / 50)
        assert activity.average_speed == pytest.approx(50 / 58)

    def test_a_length_without_a_timer_time_adds_nothing_to_the_active_time(self, tmp_path):
        activity = _payload(
            tmp_path,
            self._length(0, 1, 28),
            self._length(1, 1, 10, timed=False),
            self._length(2, 1, 30),
            self._swim_session(60),
        )["activity"]

        assert activity.total_timer_time == 58
        assert activity.pace == pytest.approx(58 / 50)


class TestSessionSport:
    def test_the_padel_sport_with_the_padel_sub_sport_is_padel(self, tmp_path):
        session = _session(40, (5, _ENUM, _SPORT_PADEL), (6, _ENUM, _SUB_SPORT_PADEL))

        assert _payload(tmp_path, session)["activity"].activity_type.name == "PADEL"

    def test_a_virtual_ride_does_not_take_its_timezone_from_the_gps_track(self, tmp_path):
        position = [(0, _SINT32, _semicircles(40)), (1, _SINT32, _semicircles(-3))]
        messages = [
            _record(0, *position),
            _session(40, (5, _ENUM, _SPORT_CYCLING), (6, _ENUM, _SUB_SPORT_VIRTUAL_ACTIVITY)),
        ]

        activity = _payload(tmp_path, *messages, timezone="Europe/Lisbon")["activity"]

        assert activity.activity_type.name == "VIRTUAL_RIDE"
        assert activity.timezone == "Europe/Lisbon"

    def test_a_real_ride_takes_its_timezone_from_the_gps_track(self, tmp_path):
        position = [(0, _SINT32, _semicircles(40)), (1, _SINT32, _semicircles(-3))]

        activity = _payload(
            tmp_path, _record(0, *position), _session(40, (5, _ENUM, _SPORT_CYCLING)), timezone="Europe/Lisbon"
        )["activity"]

        assert activity.timezone == "Europe/Madrid"


class TestSessionSummaryFallbacks:
    @staticmethod
    def _power_records(watts: int, count: int = 20) -> list[bytes]:
        return [_record(2 * i, (7, _UINT16, watts)) for i in range(count)]

    def test_a_session_without_power_takes_the_average_maximum_and_normalised_power_of_the_records(self, tmp_path):
        activity = _payload(tmp_path, *self._power_records(200), _session())["activity"]

        assert (activity.average_power, activity.max_power, activity.normalized_power) == (200, 200, 200)

    def test_a_session_with_power_but_no_normalised_power_gets_only_the_normalised_power_computed(self, tmp_path):
        activity = _payload(tmp_path, *self._power_records(200), _session(40, (20, _UINT16, 150)))["activity"]

        assert (activity.average_power, activity.max_power, activity.normalized_power) == (150, None, 200)

    def test_a_session_with_only_a_normalised_power_gets_the_average_and_maximum_computed(self, tmp_path):
        activity = _payload(tmp_path, *self._power_records(200), _session(40, (34, _UINT16, 160)))["activity"]

        assert (activity.average_power, activity.max_power, activity.normalized_power) == (200, 200, 160)

    def test_a_session_with_every_power_figure_keeps_them(self, tmp_path):
        session = _session(40, (20, _UINT16, 150), (21, _UINT16, 300), (34, _UINT16, 160))

        activity = _payload(tmp_path, *self._power_records(200), session)["activity"]

        assert (activity.average_power, activity.max_power, activity.normalized_power) == (150, 300, 160)

    def test_heart_rate_records_of_zero_are_dropouts_left_out_of_the_stream_and_the_devices_summary_stay(
        self, tmp_path
    ):
        records = [_record(5 * i, (3, _UINT8, 0)) for i in range(8)]

        payload = _payload(tmp_path, *records, _session(40, (16, _UINT8, 120), (17, _UINT8, 150)))

        activity = payload["activity"]
        assert (activity.average_hr, activity.max_hr) == (120, 150)
        # The zeros are dropouts, so the stream has no heart rate while the device's summary stays.
        assert payload["hr_waypoints"] == []

    def test_heart_rate_zeros_do_not_count_in_the_average_computed_from_the_records(self, tmp_path):
        records = [_record(10 * i, (3, _UINT8, hr)) for i, hr in enumerate([0, 100, 140, 0])]

        activity = _payload(tmp_path, *records, _session())["activity"]

        assert (activity.average_hr, activity.max_hr) == (120, 140)

    def test_the_cadence_the_session_misses_comes_from_the_records(self, tmp_path):
        records = [_record(5 * i, (4, _UINT8, 80 + 5 * i)) for i in range(8)]

        no_max = _payload(tmp_path, *records, _session(40, (18, _UINT8, 85)))["activity"]
        no_avg = _payload(tmp_path, *records, _session(40, (19, _UINT8, 99)))["activity"]

        # The records run from 80 to 115 rpm, 97.5 on average.
        assert (no_max.average_cad, no_max.max_cad) == (85, 115)
        assert (no_avg.average_cad, no_avg.max_cad) == (98, 99)

    def test_a_single_fast_fix_among_standing_ones_is_not_taken_for_the_maximum_speed(self, tmp_path):
        still = [(0, _SINT32, _semicircles(40)), (1, _SINT32, _semicircles(-3))]
        moved = [(0, _SINT32, _semicircles(40.001)), (1, _SINT32, _semicircles(-3))]
        records = [_record(second, *still) for second in range(6)] + [_record(6, *moved)]

        activity = _payload(tmp_path, *records, _session(40, (14, _UINT16, 2_000)))["activity"]

        assert activity.average_speed == 2.0
        assert activity.max_speed is None

    def test_a_session_without_a_timer_time_counts_its_elapsed_time_as_active(self, tmp_path):
        """The timer time is optional in FIT: a device that tracks no pauses reports only the elapsed time."""
        session = fit_files.raw_message(
            _SESSION,
            [
                (253, _UINT32, _fit_time(_at(40))),
                (2, _UINT32, _fit_time(_T0)),
                (7, _UINT32, 40_000),
                (9, _UINT32, 5_000),
            ],
        )

        activity = _payload(tmp_path, session)["activity"]

        assert (activity.total_elapsed_time, activity.total_timer_time, activity.distance) == (40, 40, 50)
        assert activity.pace == pytest.approx(0.8)

    def test_a_session_without_a_distance_has_no_pace_or_speeds(self, tmp_path):
        activity = _payload(tmp_path, _record(0, (3, _UINT8, 100)), _session())["activity"]

        assert (activity.distance, activity.pace, activity.average_speed, activity.max_speed) == (0, None, None, None)


class TestLapElevation:
    @staticmethod
    def _climb(seconds: int) -> list[bytes]:
        """One record a second, climbing a metre each."""
        return [_record(second, (78, _UINT32, (100 + second + 500) * 5)) for second in range(seconds)]

    def test_a_lap_without_ascent_takes_it_from_the_records_within_the_lap(self, tmp_path):
        [lap] = _payload(tmp_path, *self._climb(100), _lap(0, 100), _session(100))["laps"]

        assert lap["total_descent"] == 0
        assert 60 <= lap["total_ascent"] <= 99

    def test_a_lap_reporting_only_its_descent_gets_the_ascent_computed(self, tmp_path):
        [lap] = _payload(tmp_path, *self._climb(100), _lap(0, 100, (22, _UINT16, 7)), _session(100))["laps"]

        assert lap["total_descent"] == 7
        assert 60 <= lap["total_ascent"] <= 99

    def test_a_lap_with_no_record_inside_it_stays_without_ascent(self, tmp_path):
        payload = _payload(tmp_path, *self._climb(100), _lap(0, 100), _lap(150, 50), _session(200))

        first, second = payload["laps"]
        assert first["total_ascent"] is not None
        assert (second["total_ascent"], second["total_descent"]) == (None, None)


class TestSplittingSessions:
    def test_a_lap_without_a_start_time_belongs_to_no_session(self, tmp_path):
        lap = fit_files.raw_message(_LAP, [(253, _UINT32, _fit_time(_at(40))), (7, _UINT32, 40_000)], local_type=1)

        recorded = _decode(tmp_path, lap, _session())

        assert recorded.sessions[0].laps == ()
        assert _payload(tmp_path, lap, _session())["laps"] == []

    def test_a_lap_starting_after_the_session_ended_belongs_to_the_last_session(self, tmp_path):
        [lap] = _payload(tmp_path, _lap(100, 20), _session(40))["laps"]

        assert lap["start_time"] == _at(100)
        assert lap["total_elapsed_time"] == 20

    def test_a_file_without_laps_gives_an_activity_without_laps(self, tmp_path):
        assert _payload(tmp_path, _session())["laps"] == []

    def test_a_session_start_position_is_kept_in_the_recording(self, tmp_path):
        position = [(0, _SINT32, _semicircles(40)), (1, _SINT32, _semicircles(-3))]
        session = _session(40, (3, _SINT32, _semicircles(41)), (4, _SINT32, _semicircles(-4)))

        (decoded,) = _decode(tmp_path, _record(0, *position), session).sessions

        assert decoded.summary.start_lat == pytest.approx(41, abs=1e-6)
        assert decoded.summary.start_lon == pytest.approx(-4, abs=1e-6)

    def test_the_first_record_position_starts_the_gps_stream(self, tmp_path):
        position = [(0, _SINT32, _semicircles(40)), (1, _SINT32, _semicircles(-3))]

        payload = _payload(tmp_path, _record(0, *position), _session())

        first = payload["lat_lon_waypoints"][0]
        assert first["lat"] == pytest.approx(40, abs=1e-6)
        assert first["lon"] == pytest.approx(-3, abs=1e-6)

    @staticmethod
    def _two_sessions() -> list[bytes]:
        position = [(0, _SINT32, _semicircles(40)), (1, _SINT32, _semicircles(-3))]
        sample = [(3, _UINT8, 140), (4, _UINT8, 80), (7, _UINT16, 200), (13, _SINT8, 21), (78, _UINT32, 3_000)]
        later_start = _at(3600)
        second_record = fit_files.raw_message(
            _RECORD, [(253, _UINT32, _fit_time(later_start)), *position, *sample], local_type=2
        )
        second_session = fit_files.raw_message(
            _SESSION,
            [
                (253, _UINT32, _fit_time(later_start) + 20),
                (2, _UINT32, _fit_time(later_start)),
                (7, _UINT32, 20_000),
                (8, _UINT32, 20_000),
            ],
            local_type=3,
        )
        return [
            _record(0, *position, *sample),
            _record(10, *position, *sample),
            _session(20),
            second_record,
            second_session,
        ]

    def test_every_stream_is_cut_to_its_sessions_time_range(self, tmp_path):
        first, second = _assemble(tmp_path, *self._two_sessions())

        for stream in ("lat_lon_waypoints", "ele_waypoints", "hr_waypoints", "cad_waypoints", "power_waypoints"):
            assert [waypoint["time"] for waypoint in first[stream]] == [
                "2026-06-20T08:00:00",
                "2026-06-20T08:00:10",
            ]
            assert [waypoint["time"] for waypoint in second[stream]] == ["2026-06-20T09:00:00"]
        assert [waypoint["temp"] for waypoint in first["temp_waypoints"]] == [21, 21]
        assert second["is_temperature_set"] is True

    def test_a_record_after_the_sessions_end_belongs_to_no_session(self, tmp_path):
        records = [_record(0, (3, _UINT8, 100)), _record(20, (3, _UINT8, 105)), _record(30, (3, _UINT8, 110))]

        payload = _payload(tmp_path, *records, _session(20))

        assert [waypoint["hr"] for waypoint in payload["hr_waypoints"]] == [100, 105]

    def test_a_record_before_the_first_session_starts_belongs_to_no_session(self, tmp_path):
        later = fit_files.raw_message(
            _SESSION,
            [(253, _UINT32, _fit_time(_at(70))), (2, _UINT32, _fit_time(_at(50))), (7, _UINT32, 20_000)],
            local_type=3,
        )

        payload = _payload(tmp_path, _record(0, (3, _UINT8, 100)), _record(55, (3, _UINT8, 120)), later)

        assert [waypoint["time"] for waypoint in payload["hr_waypoints"]] == ["2026-06-20T08:00:55"]


class TestRecordEncodings:
    def test_compressed_timestamp_records_continue_from_the_last_full_timestamp(self, tmp_path):
        base = _fit_time(_T0)
        full = fit_files.raw_message(_RECORD, [(253, _UINT32, base), (3, _UINT8, 100)])
        second = fit_files.raw_message(_RECORD, [(3, _UINT8, 110)], local_type=1, time_offset=(base + 5) & 31)
        third = fit_files.raw_message(
            _RECORD, [(3, _UINT8, 120)], local_type=1, with_definition=False, time_offset=(base + 30) & 31
        )

        readings = _payload(tmp_path, full, second, third, _session())["hr_waypoints"]

        assert readings == [
            {"time": "2026-06-20T08:00:00", "hr": 100},
            {"time": "2026-06-20T08:00:05", "hr": 110},
            {"time": "2026-06-20T08:00:30", "hr": 120},
        ]

    def test_a_compressed_timestamp_offset_that_wrapped_carries_into_the_next_block(self, tmp_path):
        base = (_fit_time(_T0) & ~31) | 28
        full = fit_files.raw_message(_RECORD, [(253, _UINT32, base), (3, _UINT8, 100)])
        wrapped = fit_files.raw_message(_RECORD, [(3, _UINT8, 110)], local_type=1, time_offset=(base + 6) & 31)

        first, second = _payload(tmp_path, full, wrapped, _session())["hr_waypoints"]

        assert datetime.fromisoformat(second["time"]) - datetime.fromisoformat(first["time"]) == timedelta(seconds=6)

    def test_a_big_endian_file_decodes_like_a_little_endian_one(self, tmp_path):
        record = fit_files.raw_message(
            _RECORD,
            [
                (253, _UINT32, _fit_time(_at(60))),
                (3, _UINT8, 90),
                (7, _UINT16, 250),
                (78, _UINT32, (300 + 500) * 5),
                (0, _SINT32, _semicircles(40)),
                (1, _SINT32, _semicircles(-3)),
            ],
            big_endian=True,
        )

        payload = _payload(tmp_path, record, _session(60))

        time = "2026-06-20T08:01:00"
        assert payload["hr_waypoints"] == [{"time": time, "hr": 90}]
        assert payload["power_waypoints"] == [{"time": time, "power": 250}]
        assert payload["ele_waypoints"] == [{"time": time, "ele": 300.0}]
        [position] = payload["lat_lon_waypoints"]
        assert (position["lat"], position["lon"]) == (pytest.approx(40, abs=1e-6), pytest.approx(-3, abs=1e-6))

    def test_a_field_holding_its_invalid_value_is_absent_and_not_a_reading(self, tmp_path):
        record = _record(
            0,
            (3, _UINT8, None),
            (7, _UINT16, None),
            (78, _UINT32, None),
            (0, _SINT32, None),
            (1, _SINT32, None),
            (13, _SINT8, None),
            (4, _UINT8, None),
        )

        payload = _payload(tmp_path, record, _session())

        assert payload["hr_waypoints"] == payload["power_waypoints"] == payload["ele_waypoints"] == []
        assert payload["lat_lon_waypoints"] == payload["temp_waypoints"] == payload["cad_waypoints"] == []
        assert not any(
            (
                payload["is_heart_rate_set"],
                payload["is_power_set"],
                payload["is_elevation_set"],
                payload["is_lat_lon_set"],
                payload["is_temperature_set"],
                payload["is_cadence_set"],
            )
        )

    def test_the_plain_altitude_field_gives_the_elevation_too(self, tmp_path):
        payload = _payload(tmp_path, _record(0, (2, _UINT16, (300 + 500) * 5)), _session())

        assert payload["ele_waypoints"] == [{"time": "2026-06-20T08:00:00", "ele": 300.0}]
        assert payload["is_elevation_set"] is True

    def test_a_developer_field_leaves_the_standard_fields_decoded(self, tmp_path):
        developer_id = fit_files.raw_message(_DEVELOPER_DATA_ID, [(3, _UINT8, 0)], local_type=4)
        description = fit_files.raw_message(
            _FIELD_DESCRIPTION,
            [(0, _UINT8, 0), (1, _UINT8, 0), (2, _UINT8, _UINT16), (3, _STRING, "power"), (8, _STRING, "W")],
            local_type=5,
        )
        record = fit_files.raw_message(
            _RECORD,
            [(253, _UINT32, _fit_time(_T0)), (3, _UINT8, 100)],
            local_type=6,
            developer_fields=[(0, 0, struct.pack("<H", 321))],
        )

        payloads = _assemble(tmp_path, developer_id, description, record, _session())

        assert len(payloads) == 1
        assert payloads[0]["hr_waypoints"] == [{"time": "2026-06-20T08:00:00", "hr": 100}]

    def test_the_speed_of_a_moving_track_is_derived_from_the_positions(self, tmp_path):
        records = [
            _record(second, (0, _SINT32, _semicircles(40 + 0.0001 * second)), (1, _SINT32, _semicircles(-3)))
            for second in range(3)
        ]

        payload = _payload(tmp_path, *records, _session())

        # The first fix has nothing to measure against and keeps a 0 placeholder; 0.0001 degrees of latitude are about
        # 11.1 m, covered each second after it.
        assert [waypoint["vel"] for waypoint in payload["vel_waypoints"]] == [
            0,
            pytest.approx(11.1, abs=0.1),
            pytest.approx(11.1, abs=0.1),
        ]
        assert [waypoint["pace"] for waypoint in payload["pace_waypoints"]] == [
            pytest.approx(1 / 11.1, abs=0.001),
            pytest.approx(1 / 11.1, abs=0.001),
        ]
        assert payload["is_velocity_set"] is True

    def test_a_track_without_positions_or_device_speed_has_no_speed_stream(self, tmp_path):
        payload = _payload(tmp_path, _record(0, (3, _UINT8, 100)), _record(1, (3, _UINT8, 101)), _session())

        assert payload["vel_waypoints"] == payload["pace_waypoints"] == []
        assert payload["is_velocity_set"] is False

    def test_the_device_speed_channel_is_the_speed_stream_and_zero_speed_has_no_pace(self, tmp_path):
        records = [_record(0, (6, _UINT16, 0)), _record(1, (6, _UINT16, 2_000))]

        payload = _payload(tmp_path, *records, _session())

        assert [waypoint["vel"] for waypoint in payload["vel_waypoints"]] == [0, 2.0]
        assert [waypoint["pace"] for waypoint in payload["pace_waypoints"]] == [0.5]


class TestDamagedFiles:
    @staticmethod
    def _messages() -> list[bytes]:
        return [_record(0, (3, _UINT8, 100)), _session()]

    def test_a_wrong_footer_crc_is_tolerated(self, tmp_path):
        content = fit_files.damaged_fit_file(*self._messages(), corrupt_crc=True)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = fit_decoder.decode_fit(_write(tmp_path, content))

        assert len(result.sessions) == 1

    @pytest.mark.parametrize("cut", [1, 3, 10])
    def test_a_truncated_file_is_refused_as_invalid_input(self, tmp_path, cut):
        content = fit_files.damaged_fit_file(*self._messages(), truncate=cut)

        with pytest.raises(core_exceptions.InvalidInputError):
            fit_decoder.decode_fit(_write(tmp_path, content))

    def test_a_header_without_the_fit_signature_is_refused_as_invalid_input(self, tmp_path):
        content = bytearray(fit_files.fit_file(*self._messages()))
        content[8:12] = b".FIX"

        with pytest.raises(core_exceptions.InvalidInputError):
            fit_decoder.decode_fit(_write(tmp_path, bytes(content)))

    def test_a_data_message_of_an_undefined_local_type_is_refused_as_invalid_input(self, tmp_path):
        undefined = bytes([0x05, 0])

        with pytest.raises(core_exceptions.InvalidInputError):
            _decode(tmp_path, undefined)

    @pytest.mark.filterwarnings("ignore:invalid field size")
    def test_a_field_whose_size_does_not_fit_its_type_is_refused_as_invalid_input(self, tmp_path):
        definition = fit_files.raw_message(_RECORD, [(253, _UINT32, 5), (3, _UINT8, 100)]).replace(
            bytes([253, 4, _UINT32]), bytes([253, 3, _UINT32])
        )

        with pytest.raises(core_exceptions.InvalidInputError):
            _decode(tmp_path, definition)

    def test_a_definition_without_fields_is_refused_as_invalid_input(self, tmp_path):
        path = _write(tmp_path, struct.pack("<BBBHB", 0x40, 0, 0, _RECORD, 0) + bytes([0]))

        with pytest.raises(core_exceptions.InvalidInputError):
            fit_decoder.decode_fit(path)

    def test_two_files_chained_in_one_are_both_read(self, tmp_path):
        content = fit_files.fit_file(*self._messages())

        path = _write(tmp_path, content + content)

        assert len(fit_decoder.decode_fit(path).sessions) == 2
        assert len(assembled.assemble_fit(path)) == 2

    def test_a_file_with_only_a_header_holds_no_activity(self, tmp_path):
        assert _import(tmp_path).activities == []

    def test_a_twelve_byte_header_is_accepted(self, tmp_path):
        body = b"".join(self._messages())
        header = struct.pack("<BBHI4s", 12, 0x20, 2140, len(body), b".FIT")
        content = header + body + struct.pack("<H", fit_files._crc(header + body))

        assert len(fit_decoder.decode_fit(_write(tmp_path, content)).sessions) == 1

    def test_the_registry_parser_reads_a_file_into_one_activity(self, tmp_path):
        [parsed] = _import(tmp_path, *self._messages()).activities

        assert parsed.activity.start_time == _T0
