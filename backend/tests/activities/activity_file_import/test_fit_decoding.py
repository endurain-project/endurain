"""Tests that the FIT importer decodes real FIT bytes: message layouts, encodings, summaries and damaged files."""

import struct
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_file_import.fit_frames as fit_frames
import modules.activities.activity_file_import.fit_parser as fit_parser
import modules.activities.activity_file_import.parser_registry as registry
from tests._helpers.auth import MOCK_USER_ID
from tests.activities.activity_file_import import fit_files
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


def _parse(tmp_path: Path, *messages: bytes) -> fit_parser.FitParsePayload:
    return fit_parser.parse_fit_file(_write(tmp_path, fit_files.fit_file(*messages)))


def _import(tmp_path: Path, *messages: bytes, timezone: str = "UTC"):
    path = _write(tmp_path, fit_files.fit_file(*messages))
    parser = registry.get_parser(".fit")
    assert parser is not None
    return parser(path, MOCK_USER_ID, None, timezone, 1.0)


def _activity(tmp_path: Path, *messages: bytes, timezone: str = "UTC"):
    [parsed] = _import(tmp_path, *messages, timezone=timezone).activities
    return parsed


class TestSplitMessages:
    def test_a_split_is_decoded_in_seconds_metres_and_metres_per_second(self, tmp_path):
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
        )

        [decoded] = _parse(tmp_path, split)["splits"]

        assert decoded == {
            "split_type": "interval_active",
            "total_elapsed_time": 65.0,
            "total_timer_time": 60.0,
            "total_distance": 250.0,
            "avg_speed": 3.5,
            "start_time": _T0,
            "total_ascent": 12,
            "total_descent": 7,
            # Positions stay in semicircles, as the payload documents.
            "start_position_lat": _semicircles(40),
            "start_position_long": _semicircles(-3),
            "end_position_lat": _semicircles(41),
            "end_position_long": _semicircles(-4),
            "max_speed": 5.0,
            "end_time": _at(65),
            "total_calories": 9,
            "start_elevation": 100.0,
        }

    def test_a_split_carrying_only_its_type_leaves_every_other_field_unset(self, tmp_path):
        [decoded] = _parse(tmp_path, fit_files.raw_message(_SPLIT, [(0, _ENUM, 4)]))["splits"]

        assert decoded["split_type"] == "interval_rest"
        assert {key: value for key, value in decoded.items() if key != "split_type"} == dict.fromkeys(
            [
                "total_elapsed_time",
                "total_timer_time",
                "total_distance",
                "avg_speed",
                "start_time",
                "total_ascent",
                "total_descent",
                "start_position_lat",
                "start_position_long",
                "end_position_lat",
                "end_position_long",
                "max_speed",
                "end_time",
                "total_calories",
                "start_elevation",
            ]
        )

    def test_a_split_summary_carries_its_type_and_working_seconds(self, tmp_path):
        summary = fit_files.raw_message(_SPLIT_SUMMARY, [(0, _ENUM, 3), (4, _UINT32, 90_500)])

        assert _parse(tmp_path, summary)["split_summary"] == [
            {"split_type": "interval_active", "total_timer_time": 90.5}
        ]

    def test_a_split_summary_without_a_type_or_time_leaves_both_unset(self, tmp_path):
        summary = fit_files.raw_message(_SPLIT_SUMMARY, [(3, _UINT16, 4)])

        assert _parse(tmp_path, summary)["split_summary"] == [{"split_type": None, "total_timer_time": None}]

    def test_a_split_summary_with_an_invalid_time_leaves_it_unset(self, tmp_path):
        summary = fit_files.raw_message(_SPLIT_SUMMARY, [(0, _ENUM, 4), (4, _UINT32, None)])

        assert _parse(tmp_path, summary)["split_summary"] == [{"split_type": "interval_rest", "total_timer_time": None}]


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

        [decoded] = _parse(tmp_path, exercise_set)["sets"]

        # Duration in seconds, repetitions, weight in kg, set type, start, raw category and sub category.
        assert decoded == [30.0, 10, 20.0, "active", _T0, 28, 3]

    def test_a_rest_set_has_no_category(self, tmp_path):
        [decoded] = _parse(tmp_path, fit_files.raw_message(_SET, [(0, _UINT32, 30_000), (5, _ENUM, 0)]))["sets"]

        assert decoded == [30.0, None, None, "rest", None, None, None]

    def test_a_set_with_a_sub_category_but_no_category_takes_category_zero(self, tmp_path):
        [decoded] = _parse(tmp_path, fit_files.raw_message(_SET, [(0, _UINT32, 30_000), (8, _UINT16, 3)]))["sets"]

        assert decoded == [30.0, None, None, None, None, 0, 3]

    def test_a_set_with_category_zero_keeps_it(self, tmp_path):
        [decoded] = _parse(tmp_path, fit_files.raw_message(_SET, [(7, _UINT16, 0), (8, _UINT16, 1)]))["sets"]

        assert decoded[5:] == [0, 1]


class TestWorkoutStepMessages:
    @staticmethod
    def _step(*fields: RawField) -> bytes:
        # A step always names its duration type; the stored step requires it.
        return fit_files.raw_message(_WORKOUT_STEP, [(1, _ENUM, 0), *fields])

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

        [decoded] = _parse(tmp_path, step)["workout_steps"]

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
        [decoded] = _parse(tmp_path, self._step((3, _ENUM, 11), (4, _UINT32, 2), (7, _ENUM, 1)))["workout_steps"]

        assert (decoded.target_type, decoded.target_value, decoded.secondary_target_value) == (
            "swim_stroke",
            None,
            "breaststroke",
        )
        assert decoded.intensity == "rest"

    def test_the_any_stroke_value_of_a_swim_target_becomes_any_stroke(self, tmp_path):
        [decoded] = _parse(tmp_path, self._step((3, _ENUM, 11), (4, _UINT32, 255)))["workout_steps"]

        assert (decoded.target_value, decoded.secondary_target_value) == (None, "any stroke")

    def test_a_swim_target_with_an_unnamed_stroke_keeps_its_number(self, tmp_path):
        [decoded] = _parse(tmp_path, self._step((3, _ENUM, 11), (4, _UINT32, 9)))["workout_steps"]

        assert (decoded.target_value, decoded.secondary_target_value) == (9, None)

    def test_a_target_value_of_255_on_another_target_is_kept(self, tmp_path):
        [decoded] = _parse(tmp_path, self._step((3, _ENUM, 13), (4, _UINT32, 255)))["workout_steps"]

        assert (decoded.target_type, decoded.target_value, decoded.secondary_target_value) == (
            "heart_rate_lap",
            255,
            None,
        )

    def test_the_raw_intensity_seven_reads_as_active(self, tmp_path):
        [decoded] = _parse(tmp_path, self._step((7, _ENUM, 7)))["workout_steps"]

        assert decoded.intensity == "active"

    def test_an_exercise_name_without_a_category_takes_category_zero(self, tmp_path):
        [decoded] = _parse(tmp_path, self._step((11, _UINT16, 4)))["workout_steps"]

        assert (decoded.exercise_category, decoded.exercise_name) == (0, 4)

    def test_a_step_without_exercise_fields_leaves_them_unset(self, tmp_path):
        [decoded] = _parse(tmp_path, self._step())["workout_steps"]

        assert (decoded.exercise_category, decoded.exercise_name) == (None, None)

    def test_a_step_without_a_duration_type_is_kept_without_one(self, tmp_path):
        [decoded] = _parse(tmp_path, fit_files.raw_message(_WORKOUT_STEP, [(3, _ENUM, 1)]))["workout_steps"]

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

        assert _parse(tmp_path, step, monitoring, resting) == _parse(tmp_path, step)


class TestDeviceSettingsOffset:
    @staticmethod
    def _settings(offset: int | None) -> bytes:
        return fit_files.raw_message(_DEVICE_SETTINGS, [(2, _UINT32, offset)])

    def test_a_positive_offset_is_read_as_is(self, tmp_path):
        assert _parse(tmp_path, self._settings(3600))["time_offset"] == 3600

    def test_an_offset_written_as_an_unsigned_number_is_read_as_negative(self, tmp_path):
        assert _parse(tmp_path, self._settings(2**32 - 3600))["time_offset"] == -3600

    def test_an_invalid_offset_reads_as_none(self, tmp_path):
        assert _parse(tmp_path, self._settings(None))["time_offset"] is None

    def test_a_negative_offset_names_a_fixed_offset_zone_for_a_session_without_gps(self, tmp_path):
        activity = _activity(tmp_path, self._settings(2**32 - 5 * 3600), _session(), timezone="Europe/Paris")

        assert activity.activity.timezone == "Etc/GMT+5"

    def test_an_offset_beyond_every_real_zone_keeps_the_default_timezone(self, tmp_path):
        activity = _activity(tmp_path, self._settings(15 * 3600), _session(), timezone="Europe/Paris")

        assert activity.activity.timezone == "Europe/Paris"

    def test_a_half_hour_offset_names_a_zone_with_that_offset(self, tmp_path):
        activity = _activity(tmp_path, self._settings(19_800), _session(), timezone="Europe/Paris")

        assert activity.activity.start_time.astimezone(ZoneInfo(activity.activity.timezone)).utcoffset() == timedelta(
            seconds=19_800
        )


class TestTimezoneName:
    def test_a_whole_hour_offset_in_range_maps_to_its_fixed_offset_zone(self):
        assert fit_frames.find_timezone_name(9 * 3600, _T0) == "Etc/GMT-9"

    def test_the_largest_real_offset_maps_to_a_fixed_offset_zone(self):
        assert fit_frames.find_timezone_name(14 * 3600, _T0) == "Etc/GMT-14"

    def test_a_whole_hour_offset_past_every_zone_names_none(self):
        assert fit_frames.find_timezone_name(15 * 3600, _T0) is None


class TestPoolSwimming:
    @staticmethod
    def _length(index: int, length_type: int, seconds: int) -> bytes:
        return fit_files.raw_message(
            _LENGTH,
            [
                (254, _UINT16, index),
                (2, _UINT32, _fit_time(_at(30 * index))),
                (3, _UINT32, seconds * 1000),
                (4, _UINT32, seconds * 1000),
                (5, _UINT16, 18),
                (6, _UINT16, 1_200),
                (7, _ENUM, 2),
                (9, _UINT8, 30),
                (12, _ENUM, length_type),
            ],
            local_type=1,
        )

    def test_a_length_is_decoded(self, tmp_path):
        [length] = _parse(tmp_path, self._length(0, 1, 28))["lengths"]

        assert length == {
            "message_index": 0,
            "start_time": _T0,
            "total_elapsed_time": 28.0,
            "total_timer_time": 28.0,
            "total_strokes": 18,
            "avg_speed": 1.2,
            "swim_stroke": "breaststroke",
            "avg_swimming_cadence": 30,
            "length_type": "active",
        }

    def test_the_active_time_and_pace_count_only_the_active_lengths(self, tmp_path):
        activity = _activity(
            tmp_path,
            self._length(0, 1, 28),
            self._length(1, 0, 10),
            self._length(2, 1, 30),
            _session(
                60,
                (5, _ENUM, _SPORT_SWIMMING),
                (6, _ENUM, _SUB_SPORT_LAP_SWIMMING),
                (9, _UINT32, 5_000),
            ),
        ).activity

        assert activity.activity_type.name == "LAP_SWIMMING"
        assert activity.distance == 50
        assert activity.total_timer_time == 58
        assert activity.pace == pytest.approx(58 / 50)
        assert activity.average_speed == pytest.approx(50 / 58)


class TestSessionSport:
    def test_the_padel_sport_with_the_padel_sub_sport_is_padel(self, tmp_path):
        activity = _activity(tmp_path, _session(40, (5, _ENUM, _SPORT_PADEL), (6, _ENUM, _SUB_SPORT_PADEL))).activity

        assert activity.activity_type.name == "PADEL"

    def test_a_virtual_ride_does_not_take_its_timezone_from_the_gps_track(self, tmp_path):
        position = [(0, _SINT32, _semicircles(40)), (1, _SINT32, _semicircles(-3))]
        messages = [
            _record(0, *position),
            _session(40, (5, _ENUM, _SPORT_CYCLING), (6, _ENUM, _SUB_SPORT_VIRTUAL_ACTIVITY)),
        ]

        activity = _activity(tmp_path, *messages, timezone="Europe/Lisbon").activity

        assert activity.activity_type.name == "VIRTUAL_RIDE"
        assert activity.timezone == "Europe/Lisbon"

    def test_a_real_ride_takes_its_timezone_from_the_gps_track(self, tmp_path):
        position = [(0, _SINT32, _semicircles(40)), (1, _SINT32, _semicircles(-3))]

        activity = _activity(
            tmp_path, _record(0, *position), _session(40, (5, _ENUM, _SPORT_CYCLING)), timezone="Europe/Lisbon"
        ).activity

        assert activity.timezone == "Europe/Madrid"


class TestSessionSummaryFallbacks:
    @staticmethod
    def _power_records(watts: int, count: int = 20) -> list[bytes]:
        return [_record(2 * i, (7, _UINT16, watts)) for i in range(count)]

    def test_a_session_without_power_takes_the_average_maximum_and_normalised_power_of_the_records(self, tmp_path):
        activity = _activity(tmp_path, *self._power_records(200), _session()).activity

        assert (activity.average_power, activity.max_power, activity.normalized_power) == (200, 200, 200)

    def test_a_session_with_power_but_no_normalised_power_gets_only_the_normalised_power_computed(self, tmp_path):
        activity = _activity(tmp_path, *self._power_records(200), _session(40, (20, _UINT16, 150))).activity

        assert (activity.average_power, activity.max_power, activity.normalized_power) == (150, None, 200)

    def test_a_session_with_only_a_normalised_power_gets_the_average_and_maximum_computed(self, tmp_path):
        activity = _activity(tmp_path, *self._power_records(200), _session(40, (34, _UINT16, 160))).activity

        assert (activity.average_power, activity.max_power, activity.normalized_power) == (200, 200, 160)

    def test_a_session_with_every_power_figure_keeps_them(self, tmp_path):
        session = _session(40, (20, _UINT16, 150), (21, _UINT16, 300), (34, _UINT16, 160))

        activity = _activity(tmp_path, *self._power_records(200), session).activity

        assert (activity.average_power, activity.max_power, activity.normalized_power) == (150, 300, 160)

    def test_heart_rate_records_of_zero_leave_the_devices_summary(self, tmp_path):
        records = [_record(5 * i, (3, _UINT8, 0)) for i in range(8)]

        activity = _activity(tmp_path, *records, _session(40, (16, _UINT8, 120), (17, _UINT8, 150))).activity

        assert (activity.average_hr, activity.max_hr) == (120, 150)

    def test_the_cadence_the_session_misses_comes_from_the_records(self, tmp_path):
        records = [_record(5 * i, (4, _UINT8, 80 + 5 * i)) for i in range(8)]

        no_max = _activity(tmp_path, *records, _session(40, (18, _UINT8, 85))).activity
        no_avg = _activity(tmp_path, *records, _session(40, (19, _UINT8, 99))).activity

        # The records run from 80 to 115 rpm, 97.5 on average.
        assert (no_max.average_cad, no_max.max_cad) == (85, 115)
        assert (no_avg.average_cad, no_avg.max_cad) == (98, 99)

    def test_a_single_fast_fix_among_standing_ones_is_not_taken_for_the_maximum_speed(self, tmp_path):
        still = [(0, _SINT32, _semicircles(40)), (1, _SINT32, _semicircles(-3))]
        moved = [(0, _SINT32, _semicircles(40.001)), (1, _SINT32, _semicircles(-3))]
        records = [_record(second, *still) for second in range(6)] + [_record(6, *moved)]

        activity = _activity(tmp_path, *records, _session(40, (14, _UINT16, 2_000))).activity

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

        activity = _activity(tmp_path, session).activity

        assert (activity.total_elapsed_time, activity.total_timer_time, activity.distance) == (40, 40, 50)
        assert activity.pace == pytest.approx(0.8)


class TestLapElevation:
    @staticmethod
    def _climb(seconds: int) -> list[bytes]:
        """One record a second, climbing a metre each."""
        return [_record(second, (78, _UINT32, (100 + second + 500) * 5)) for second in range(seconds)]

    def test_a_lap_without_ascent_takes_it_from_the_records_within_the_lap(self, tmp_path):
        activity = _activity(tmp_path, *self._climb(100), _lap(0, 100), _session(100))

        [lap] = activity.components["laps"]
        assert lap["total_descent"] == 0
        assert 60 <= lap["total_ascent"] <= 99

    def test_a_lap_reporting_only_its_descent_gets_the_ascent_computed(self, tmp_path):
        activity = _activity(tmp_path, *self._climb(100), _lap(0, 100, (22, _UINT16, 7)), _session(100))

        [lap] = activity.components["laps"]
        assert lap["total_descent"] == 7
        assert 60 <= lap["total_ascent"] <= 99

    def test_a_lap_with_no_record_inside_it_stays_without_ascent(self, tmp_path):
        activity = _activity(tmp_path, *self._climb(100), _lap(0, 100), _lap(150, 50), _session(200))

        first, second = activity.components["laps"]
        assert first["total_ascent"] is not None
        assert (second["total_ascent"], second["total_descent"]) == (None, None)


class TestSplittingSessions:
    def test_a_lap_without_a_start_time_belongs_to_no_session(self, tmp_path):
        lap = fit_files.raw_message(_LAP, [(253, _UINT32, _fit_time(_at(40))), (7, _UINT32, 40_000)], local_type=1)

        activity = _activity(tmp_path, lap, _session())

        assert activity.components["laps"] == []

    def test_a_lap_starting_after_the_session_ended_belongs_to_no_session(self, tmp_path):
        activity = _activity(tmp_path, _lap(100, 20), _session(40))

        assert activity.components["laps"] == []

    def test_a_file_without_laps_gives_an_activity_without_laps(self, tmp_path):
        assert _activity(tmp_path, _session()).components["laps"] == []

    def test_a_session_start_position_is_kept_when_the_records_carry_a_position(self, tmp_path):
        position = [(0, _SINT32, _semicircles(40)), (1, _SINT32, _semicircles(-3))]
        session = _session(40, (3, _SINT32, _semicircles(41)), (4, _SINT32, _semicircles(-4)))

        payload = _parse(tmp_path, _record(0, *position), session)
        [record] = fit_parser.split_records_by_activity(payload)

        assert record["session"]["initial_latitude"] == pytest.approx(41, abs=1e-6)
        assert record["session"]["initial_longitude"] == pytest.approx(-4, abs=1e-6)

    def test_a_session_without_a_start_position_takes_the_first_record_position(self, tmp_path):
        position = [(0, _SINT32, _semicircles(40)), (1, _SINT32, _semicircles(-3))]

        payload = _parse(tmp_path, _record(0, *position), _session())
        [record] = fit_parser.split_records_by_activity(payload)

        assert record["session"]["initial_latitude"] == pytest.approx(40, abs=1e-6)
        assert record["session"]["initial_longitude"] == pytest.approx(-3, abs=1e-6)

    def test_every_stream_is_cut_to_its_sessions_time_range(self, tmp_path):
        position = [(0, _SINT32, _semicircles(40)), (1, _SINT32, _semicircles(-3))]
        sample = [(3, _UINT8, 140), (4, _UINT8, 80), (7, _UINT16, 200), (13, _SINT8, 21), (78, _UINT32, 3_000)]
        first = [_record(0, *position, *sample), _record(10, *position, *sample), _session(20)]
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

        records = fit_parser.split_records_by_activity(_parse(tmp_path, *first, second_record, second_session))

        first_record, second_session_record = records
        for stream in ("lat_lon_waypoints", "ele_waypoints", "hr_waypoints", "cad_waypoints", "power_waypoints"):
            assert [waypoint["time"] for waypoint in first_record[stream]] == [
                "2026-06-20T08:00:00",
                "2026-06-20T08:00:10",
            ]
            assert [waypoint["time"] for waypoint in second_session_record[stream]] == ["2026-06-20T09:00:00"]
        assert [waypoint["temp"] for waypoint in first_record["temp_waypoints"]] == [21, 21]
        assert second_session_record["is_temperature_set"] is True


class TestRecordEncodings:
    def test_compressed_timestamp_records_continue_from_the_last_full_timestamp(self, tmp_path):
        base = _fit_time(_T0)
        full = fit_files.raw_message(_RECORD, [(253, _UINT32, base), (3, _UINT8, 100)])
        second = fit_files.raw_message(_RECORD, [(3, _UINT8, 110)], local_type=1, time_offset=(base + 5) & 31)
        third = fit_files.raw_message(
            _RECORD, [(3, _UINT8, 120)], local_type=1, with_definition=False, time_offset=(base + 30) & 31
        )

        readings = _parse(tmp_path, full, second, third)["hr_waypoints"]

        assert readings == [
            {"time": "2026-06-20T08:00:00", "hr": 100},
            {"time": "2026-06-20T08:00:05", "hr": 110},
            {"time": "2026-06-20T08:00:30", "hr": 120},
        ]

    def test_a_compressed_timestamp_offset_that_wrapped_carries_into_the_next_block(self, tmp_path):
        base = (_fit_time(_T0) & ~31) | 28
        full = fit_files.raw_message(_RECORD, [(253, _UINT32, base), (3, _UINT8, 100)])
        wrapped = fit_files.raw_message(_RECORD, [(3, _UINT8, 110)], local_type=1, time_offset=(base + 6) & 31)

        first, second = _parse(tmp_path, full, wrapped)["hr_waypoints"]

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

        payload = _parse(tmp_path, record)

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

        payload = _parse(tmp_path, record)

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
        payload = _parse(tmp_path, _record(0, (2, _UINT16, (300 + 500) * 5)))

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

        payload = _parse(tmp_path, developer_id, description, record, _session())

        assert payload["hr_waypoints"] == [{"time": "2026-06-20T08:00:00", "hr": 100}]
        assert len(payload["sessions"]) == 1

    def test_a_velocity_of_a_moving_track_is_derived_from_the_positions(self, tmp_path):
        records = [
            _record(second, (0, _SINT32, _semicircles(40 + 0.0001 * second)), (1, _SINT32, _semicircles(-3)))
            for second in range(3)
        ]

        payload = _parse(tmp_path, *records)

        # 0.0001 degrees of latitude are about 11.1 m, covered each second.
        assert [waypoint["vel"] for waypoint in payload["vel_waypoints"]] == [
            pytest.approx(11.1, abs=0.1),
            pytest.approx(11.1, abs=0.1),
        ]
        assert payload["is_velocity_set"] is True


class TestDamagedFiles:
    @staticmethod
    def _messages() -> list[bytes]:
        return [_record(0, (3, _UINT8, 100)), _session()]

    def test_a_wrong_footer_crc_is_tolerated(self, tmp_path):
        content = fit_files.damaged_fit_file(*self._messages(), corrupt_crc=True)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            payload = fit_parser.parse_fit_file(_write(tmp_path, content))

        assert len(payload["sessions"]) == 1

    @pytest.mark.parametrize("cut", [1, 3, 10])
    def test_a_truncated_file_is_refused_as_invalid_input(self, tmp_path, cut):
        content = fit_files.damaged_fit_file(*self._messages(), truncate=cut)

        with pytest.raises(core_exceptions.InvalidInputError):
            fit_parser.parse_fit_file(_write(tmp_path, content))

    def test_a_header_without_the_fit_signature_is_refused_as_invalid_input(self, tmp_path):
        content = bytearray(fit_files.fit_file(*self._messages()))
        content[8:12] = b".FIX"

        with pytest.raises(core_exceptions.InvalidInputError):
            fit_parser.parse_fit_file(_write(tmp_path, bytes(content)))

    def test_a_data_message_of_an_undefined_local_type_is_refused_as_invalid_input(self, tmp_path):
        undefined = bytes([0x05, 0])

        with pytest.raises(core_exceptions.InvalidInputError):
            _parse(tmp_path, undefined)

    @pytest.mark.filterwarnings("ignore:invalid field size")
    def test_a_field_whose_size_does_not_fit_its_type_is_refused_as_invalid_input(self, tmp_path):
        definition = fit_files.raw_message(_RECORD, [(253, _UINT32, 5), (3, _UINT8, 100)]).replace(
            bytes([253, 4, _UINT32]), bytes([253, 3, _UINT32])
        )

        with pytest.raises(core_exceptions.InvalidInputError):
            _parse(tmp_path, definition)

    def test_a_definition_without_fields_is_refused_as_invalid_input(self, tmp_path):
        with pytest.raises(core_exceptions.InvalidInputError):
            _parse(tmp_path, struct.pack("<BBBHB", 0x40, 0, 0, _RECORD, 0) + bytes([0]))

    def test_two_files_chained_in_one_are_both_read(self, tmp_path):
        content = fit_files.fit_file(*self._messages())

        payload = fit_parser.parse_fit_file(_write(tmp_path, content + content))

        assert len(payload["sessions"]) == 2

    def test_a_file_with_only_a_header_holds_no_activity(self, tmp_path):
        assert _import(tmp_path).activities == []

    def test_a_twelve_byte_header_is_accepted(self, tmp_path):
        body = b"".join(self._messages())
        header = struct.pack("<BBHI4s", 12, 0x20, 2140, len(body), b".FIT")
        content = header + body + struct.pack("<H", fit_files._crc(header + body))

        assert len(fit_parser.parse_fit_file(_write(tmp_path, content))["sessions"]) == 1
