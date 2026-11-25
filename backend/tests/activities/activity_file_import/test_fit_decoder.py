"""Tests that the FIT decoder turns real and synthetic FIT files into the right recording."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import fitdecode
import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_file_import.fit_decoder as fit_decoder
import modules.activities.activity_file_import.recording as recording
import modules.activities.computation as activities_computation
from tests.activities.activity_file_import import fit_files, synthetic_files

_FIXTURES = Path(__file__).parent / "fixtures"

_UINT8 = 0x02
_UINT32 = 0x86
_RECORD = 20
_SESSION = 18


def _real(case: str) -> recording.Recording:
    (path,) = (_FIXTURES / case).glob("*.fit")
    return fit_decoder.decode_fit(str(path))


def _synthetic(name: str, tmp_path: Path) -> recording.Recording:
    path = tmp_path / f"{name}.fit"
    path.write_bytes(synthetic_files.CASES[f"fit/{name}.fit"]())
    return fit_decoder.decode_fit(str(path))


def _decode(tmp_path: Path, content: bytes) -> recording.Recording:
    path = tmp_path / "file.fit"
    path.write_bytes(content)
    return fit_decoder.decode_fit(str(path))


class TestRealFiles:
    def test_triathlon_has_five_sessions_with_each_record_and_lap_once(self):
        path = next((_FIXTURES / "triathlon").glob("*.fit"))
        timed_records = sum(
            1
            for frame in fitdecode.FitReader(str(path))
            if isinstance(frame, fitdecode.FitDataMessage)
            and frame.name == "record"
            and isinstance(frame.get_value("timestamp", fallback=None), datetime)
        )
        result = fit_decoder.decode_fit(str(path))

        assert [session.sport for session in result.sessions] == [
            "open_water",
            "transition",
            "cycling",
            "transition",
            "running",
        ]
        # The run's device session ends at 12:42:36.458; the two records written after it belong to no session.
        assert sum(len(session.samples) for session in result.sessions) == timed_records - 2
        assert [len(session.laps) for session in result.sessions] == [1, 1, 2, 1, 4]
        assert sum(len(session.laps) for session in result.sessions) == 9
        starts = [session.start_time for session in result.sessions]
        assert starts == sorted(starts)
        for session, end in zip(result.sessions, [*starts[1:], None], strict=True):
            assert all(session.start_time <= moment for moment in session.samples.time)
            assert all(end is None or moment < end for moment in session.samples.time)
            assert all(
                lap.start_time >= session.start_time and (end is None or lap.start_time < end) for lap in session.laps
            )

    def test_triathlon_split_summaries_follow_the_leg_they_precede(self):
        result = _real("triathlon")

        assert [len(session.split_summaries) for session in result.sessions] == [0, 0, 0, 0, 3]

    @pytest.mark.parametrize("case", ["indoor_ride", "treadmill_run"])
    def test_indoor_files_carry_distance_and_speed(self, case):
        (session,) = _real(case).sessions

        assert any(value for value in session.samples.distance)
        assert any(value for value in session.samples.speed)
        assert session.summary.distance

    def test_pool_swim_keeps_every_length_in_its_session(self):
        (session,) = _real("pool_swim").sessions

        assert len(session.lengths) == 68
        assert sum(length.length_type == "active" for length in session.lengths) == 63
        assert sum(length.length_type == "idle" for length in session.lengths) == 5

    @pytest.mark.parametrize("case", ["strength", "hiit"])
    def test_strength_files_carry_sets(self, case):
        (session,) = _real(case).sessions

        assert session.sets

    def test_outdoor_ride_pauses_pair_each_timer_stop_with_its_restart(self):
        (session,) = _real("outdoor_ride").sessions

        assert [(pause.start.time().isoformat(), pause.end.time().isoformat()) for pause in session.pauses] == [
            ("08:50:55", "08:52:02"),
            ("09:38:36", "09:38:49"),
        ]

    def test_outdoor_run_carries_its_workout_step(self):
        result = _real("outdoor_run")

        assert result.sessions[0].workout_steps
        assert result.name == "Base"
        assert result.manufacturer == "garmin"
        assert result.local_time_offset == 3600
        assert result.device_time_offset == 3600


class TestSyntheticFiles:
    def test_a_developer_field_fills_the_power_channel(self, tmp_path):
        (session,) = _synthetic("stryd_developer_power", tmp_path).sessions

        assert session.samples.power[0] == 240
        assert session.samples.power[1] == 241
        assert all(value is not None for value in session.samples.power)

    def test_the_boundary_record_and_lap_go_to_the_second_session_only(self, tmp_path):
        first, second = _synthetic("multisport_boundary", tmp_path).sessions

        boundary = second.start_time
        assert boundary not in first.samples.time
        assert second.samples.time[0] == boundary
        assert [lap.start_time for lap in first.laps] == [first.start_time]
        assert [lap.start_time for lap in second.laps] == [boundary]

    def test_each_pool_session_has_only_its_own_lengths(self, tmp_path):
        first, second = _synthetic("two_pool_sessions", tmp_path).sessions

        assert len(first.lengths) == len(second.lengths) == 4
        assert all(length.start_time < second.start_time for length in first.lengths if length.start_time)
        assert all(length.start_time >= second.start_time for length in second.lengths if length.start_time)

    def test_a_length_without_timer_time_decodes_with_none(self, tmp_path):
        (session,) = _synthetic("lap_swim_missing_length_time", tmp_path).sessions

        assert len(session.lengths) == 3
        assert sum(length.total_timer_time is None for length in session.lengths) == 1

    def test_a_record_without_timestamp_is_skipped(self, tmp_path):
        (session,) = _synthetic("record_without_timestamp", tmp_path).sessions

        assert len(session.samples) == 60

    def test_records_on_an_unset_clock_are_skipped(self, tmp_path):
        records = [
            fit_files.raw_message(_RECORD, [(253, _UINT32, 5_000 + second), (3, _UINT8, 140)], local_type=2)
            for second in range(5)
        ]
        start = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
        good = fit_files.message("record", 1, timestamp=start, heart_rate=150)
        session = fit_files.message("session", 3, timestamp=start, start_time=start, total_elapsed_time=1, sport=1)

        result = _decode(tmp_path, fit_files.fit_file(*records, good, session))

        assert len(result.sessions[0].samples) == 1

    def test_a_session_on_an_unset_clock_is_refused(self, tmp_path):
        with pytest.raises(core_exceptions.InvalidInputError, match="A FIT session has no start time"):
            _synthetic("unset_clock", tmp_path)

    def test_a_session_without_start_time_is_refused(self, tmp_path):
        with pytest.raises(core_exceptions.InvalidInputError, match="A FIT session has no start time"):
            _synthetic("session_without_start_time", tmp_path)

    def test_records_without_a_session_are_refused(self, tmp_path):
        with pytest.raises(core_exceptions.InvalidInputError, match="The FIT file has no session"):
            _synthetic("no_session", tmp_path)

    def test_many_sessions_decode_as_many_sessions(self, tmp_path):
        assert len(_synthetic("many_sessions", tmp_path).sessions) == 12

    @pytest.mark.parametrize(("name", "sport"), [("padel", "padel"), ("hiit", "hiit")])
    def test_sport_resolves_by_name(self, tmp_path, name, sport):
        (session,) = _synthetic(name, tmp_path).sessions

        assert session.sport == sport

    def test_a_ride_decodes_every_record_and_its_summary(self, tmp_path):
        (session,) = _synthetic("ride_power_pauses", tmp_path).sessions

        assert len(session.samples) == 240
        assert session.summary.total_timer_time is not None

    def test_a_session_without_timer_time_keeps_none(self, tmp_path):
        start = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
        session = fit_files.message(
            "session", 3, timestamp=start + timedelta(seconds=60), start_time=start, total_elapsed_time=60, sport=1
        )

        (decoded,) = _decode(tmp_path, fit_files.fit_file(session)).sessions

        assert decoded.summary.total_timer_time is None
        assert decoded.summary.total_elapsed_time == 60


class TestFileLimits:
    def test_a_file_past_the_sample_limit_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(recording, "MAX_SAMPLES_PER_FILE", 10)

        with pytest.raises(core_exceptions.InvalidInputError, match="more than 10 samples"):
            _synthetic("gps_spike", tmp_path)

    def test_a_file_past_the_session_limit_is_refused(self, tmp_path, monkeypatch):
        monkeypatch.setattr(recording, "MAX_SESSIONS_PER_FILE", 3)

        with pytest.raises(core_exceptions.InvalidInputError, match="more than 3 sessions"):
            _synthetic("many_sessions", tmp_path)


class TestDamagedFiles:
    def test_a_truncated_file_is_refused(self, tmp_path):
        content = fit_files.damaged_fit_file(fit_files.message("workout", wkt_name="x"), truncate=6)

        with pytest.raises(core_exceptions.InvalidInputError, match="Can't parse FIT file"):
            _decode(tmp_path, content)

    def test_a_wrong_footer_crc_is_tolerated(self, tmp_path):
        start = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
        session = fit_files.message("session", 3, timestamp=start, start_time=start, total_elapsed_time=1, sport=1)

        with pytest.warns(UserWarning):
            result = _decode(tmp_path, fit_files.damaged_fit_file(session, corrupt_crc=True))

        assert len(result.sessions) == 1


_UINT16 = 0x84
_STRING = 0x07
_LAP = 19
_FILE_ID = 0
_EXERCISE_TITLE = 264
_T0 = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)


def _fit_second(moment: datetime) -> int:
    return int((moment - fit_files._FIT_EPOCH).total_seconds())


def _session_message(local_type: int = 3) -> bytes:
    return fit_files.message(
        "session", local_type, timestamp=_T0, start_time=_T0, total_elapsed_time=60, total_timer_time=60, sport=1
    )


class _MockFrame:
    """Minimal stand-in for a fitdecode data message with decoded values."""

    def __init__(self, **values):
        self._values = values

    def get_value(self, key, default=None):
        return self._values.get(key, default)


class _RaisingFrame:
    """Frame whose get_value always raises KeyError (unknown field)."""

    def get_value(self, key):
        raise KeyError(key)


class _RawFrame:
    """Frame exposing get_raw_value, mimicking fitdecode raw field access."""

    def __init__(self, **values):
        self._values = values

    def get_raw_value(self, key):
        if key not in self._values:
            raise KeyError(key)
        return self._values[key]


class _ExerciseTitleFrame:
    """Frame exposing both get_value and get_raw_value over one field dict, like fitdecode."""

    name = "exercise_title"

    def __init__(self, **values):
        self._values = values

    def get_value(self, key):
        return self._values.get(key)

    def get_raw_value(self, key):
        return self._values.get(key)


class TestManufacturerAndProduct:
    def test_numeric_manufacturer_and_product_are_stringified(self, tmp_path):
        # Some devices (e.g. Amazfit/Zepp) report an unmapped numeric manufacturer id rather than a name.
        file_id = fit_files.raw_message(_FILE_ID, [(1, _UINT16, 339), (2, _UINT16, 4567)], local_type=2)

        result = _decode(tmp_path, fit_files.fit_file(file_id, _session_message()))

        assert result.manufacturer == "339"
        assert result.product == "4567"

    def test_missing_manufacturer_and_product_stay_none(self, tmp_path):
        result = _decode(tmp_path, fit_files.fit_file(_session_message()))

        assert result.manufacturer is None
        assert result.product is None


class TestSportResolution:
    """resolve_sport maps a frame's sport and sub sport to the activity type name."""

    @staticmethod
    def _sport(sport="running", sub_sport=None):
        return fit_decoder.resolve_sport(_MockFrame(sport=sport, sub_sport=sub_sport))

    def test_cycling_indoor_cycling_is_not_flattened(self):
        assert self._sport("cycling", "indoor_cycling") == "indoor_cycling"

    def test_cycling_virtual_activity_is_virtual_ride(self):
        assert self._sport("cycling", "virtual_activity") == "virtual_ride"

    def test_cycling_commuting_is_commuting_ride(self):
        assert self._sport("cycling", "commuting") == "commuting_ride"

    def test_cycling_mixed_surface_is_mixed_surface_ride(self):
        assert self._sport("cycling", "mixed_surface") == "mixed_surface_ride"

    def test_cycling_generic_sub_sport_keeps_the_sport(self):
        assert self._sport("cycling", "generic") == "cycling"

    def test_cycling_without_sub_sport_keeps_the_sport(self):
        assert self._sport("cycling", None) == "cycling"

    def test_running_indoor_running_takes_the_sub_sport(self):
        assert self._sport("running", "indoor_running") == "indoor_running"

    def test_running_generic_sub_sport_keeps_the_sport(self):
        assert self._sport("running", "generic") == "running"

    def test_running_treadmill_takes_the_sub_sport(self):
        assert self._sport("running", "treadmill") == "treadmill"

    def test_generic_with_breathing_is_hiit(self):
        assert self._sport("generic", "breathing") == "hiit"

    def test_unknown_sub_sport_keeps_the_sport(self):
        assert self._sport("running", "ultramarathon") == "running"

    def test_running_street_sub_sport_keeps_the_sport(self):
        """Regression for #866."""
        assert self._sport("running", "street") == "running"

    def test_a_frame_without_sport_is_a_workout(self):
        assert fit_decoder.resolve_sport(_MockFrame()) == "Workout"


class TestSessionSummary:
    def test_zero_workout_rpe_is_unset(self, tmp_path):
        """Polar writes workout_rpe=0 when no RPE was entered (#820); it is decoded as None."""
        session = fit_files.raw_message(
            _SESSION,
            [(253, _UINT32, _fit_second(_T0)), (2, _UINT32, _fit_second(_T0)), (193, _UINT16, 0)],
            local_type=2,
        )

        (decoded,) = _decode(tmp_path, fit_files.fit_file(session)).sessions

        assert decoded.summary.workout_rpe is None


class TestGetValueFromFrame:
    def test_genuine_zero_survives(self):
        """A real 0 (e.g. 0 m ascent) is returned, not replaced by the default."""
        assert fit_decoder.get_value_from_frame(_MockFrame(total_ascent=0), "total_ascent", 99) == 0

    def test_none_falls_back_to_default(self):
        assert fit_decoder.get_value_from_frame(_MockFrame(total_ascent=None), "total_ascent", 99) == 99

    def test_present_value_returned(self):
        assert fit_decoder.get_value_from_frame(_MockFrame(avg_power=210), "avg_power") == 210

    def test_keyerror_falls_back_to_default(self):
        assert fit_decoder.get_value_from_frame(_RaisingFrame(), "missing", "d") == "d"


class TestRecordCadence:
    """A record's fractional cadence is folded into its cadence sample."""

    @staticmethod
    def _cadence(tmp_path, cadence=None, fraction=None):
        fields = [(253, _UINT32, _fit_second(_T0))]
        if cadence is not None:
            fields.append((4, _UINT8, cadence))
        if fraction is not None:
            fields.append((53, _UINT8, round(fraction * 128)))
        record = fit_files.raw_message(_RECORD, fields, local_type=2)
        (session,) = _decode(tmp_path, fit_files.fit_file(record, _session_message())).sessions
        return session.samples.cadence[0]

    def test_folds_the_fraction(self, tmp_path):
        assert self._cadence(tmp_path, cadence=85, fraction=0.5) == 85.5

    def test_keeps_cadence_without_a_fraction(self, tmp_path):
        assert self._cadence(tmp_path, cadence=85) == 85

    def test_missing_cadence_stays_none(self, tmp_path):
        assert self._cadence(tmp_path, fraction=0.5) is None

    def test_running_stream_doubles_the_folded_fraction(self, tmp_path):
        waypoints = activities_computation.double_cadence_waypoints(
            [{"time": "t0", "cad": self._cadence(tmp_path, cadence=85, fraction=0.5)}]
        )
        assert waypoints == [{"time": "t0", "cad": 171}]


class TestLapSpeed:
    """A lap reads its enhanced speed fields before the legacy ones."""

    @staticmethod
    def _lap(tmp_path, fields):
        lap = fit_files.raw_message(
            _LAP, [(253, _UINT32, _fit_second(_T0)), (2, _UINT32, _fit_second(_T0)), *fields], local_type=2
        )
        (session,) = _decode(tmp_path, fit_files.fit_file(lap, _session_message())).sessions
        (decoded,) = session.laps
        return decoded

    def test_enhanced_speed_is_preferred(self, tmp_path):
        lap = self._lap(
            tmp_path, [(110, _UINT32, 4000), (111, _UINT32, 5000), (13, _UINT16, 1000), (14, _UINT16, 2000)]
        )

        assert lap.avg_speed == 4.0
        assert lap.max_speed == 5.0

    def test_falls_back_to_legacy_speed(self, tmp_path):
        lap = self._lap(tmp_path, [(13, _UINT16, 2500), (14, _UINT16, 5000)])

        assert lap.avg_speed == 2.5
        assert lap.max_speed == 5.0

    def test_no_speed_fields_leave_none(self, tmp_path):
        lap = self._lap(tmp_path, [(9, _UINT32, 100_000), (8, _UINT32, 250_000)])

        assert lap.avg_speed is None
        assert lap.max_speed is None
        assert lap.total_distance == 1000
        assert lap.total_timer_time == 250


class TestParseFrameActivity:
    """parse_frame_activity derives the UTC offset from local_timestamp - timestamp."""

    def test_returns_positive_offset(self):
        frame = _RawFrame(timestamp=1_000_000, local_timestamp=1_007_200)
        assert fit_decoder.parse_frame_activity(frame) == 7200

    def test_returns_negative_offset(self):
        frame = _RawFrame(timestamp=1_000_000, local_timestamp=982_000)
        assert fit_decoder.parse_frame_activity(frame) == -18_000

    def test_none_when_local_timestamp_missing(self):
        assert fit_decoder.parse_frame_activity(_RawFrame(timestamp=1_000_000)) is None

    def test_none_when_timestamp_missing(self):
        assert fit_decoder.parse_frame_activity(_RawFrame(local_timestamp=1_000_000)) is None

    def test_none_when_offset_beyond_utc_plus_14(self):
        frame = _RawFrame(timestamp=1_000_000, local_timestamp=1_000_000 + 15 * 3600)
        assert fit_decoder.parse_frame_activity(frame) is None

    def test_none_when_offset_beyond_utc_minus_12(self):
        frame = _RawFrame(timestamp=1_000_000, local_timestamp=1_000_000 - 13 * 3600)
        assert fit_decoder.parse_frame_activity(frame) is None

    def test_accepts_utc_plus_14_boundary(self):
        frame = _RawFrame(timestamp=1_000_000, local_timestamp=1_000_000 + 14 * 3600)
        assert fit_decoder.parse_frame_activity(frame) == 14 * 3600

    def test_an_activity_message_sets_the_recording_local_offset(self, tmp_path):
        activity = fit_files.message("activity", 2, timestamp=_T0, local_timestamp=_T0 + timedelta(hours=2))

        result = _decode(tmp_path, fit_files.fit_file(activity, _session_message()))

        assert result.local_time_offset == 7200


class TestMalformedFitFile:
    """A file that is not a valid FIT is the uploader's fault, so retrying the job cannot help.

    A record without its timestamp is skipped (``TestSyntheticFiles.test_a_record_without_timestamp_is_skipped``),
    and a truncated file is refused (``TestDamagedFiles.test_a_truncated_file_is_refused``).
    """

    def test_garbage_is_rejected_as_invalid_input(self, tmp_path):
        with pytest.raises(core_exceptions.InvalidInputError, match="Can't parse FIT file"):
            _decode(tmp_path, b"\x00" * 40)

    def test_a_file_that_cannot_be_opened_stays_a_processing_error(self, tmp_path):
        with pytest.raises(core_exceptions.ProcessingError):
            fit_decoder.decode_fit(str(tmp_path / "missing.fit"))


class TestParseFrameExerciseTitle:
    """parse_frame_exercise_title returns a title only when the step name and both codes are present."""

    def test_normal_frame_returns_title(self):
        frame = _ExerciseTitleFrame(wkt_step_name="Bench Press", exercise_category=0, exercise_name=5)
        title = fit_decoder.parse_frame_exercise_title(frame)
        assert title.wkt_step_name == "Bench Press"
        assert title.exercise_category == 0
        assert title.exercise_name == 5

    def test_missing_name_returns_none(self):
        frame = _ExerciseTitleFrame(exercise_category=1, exercise_name=2)
        assert fit_decoder.parse_frame_exercise_title(frame) is None

    def test_blank_name_returns_none(self):
        frame = _ExerciseTitleFrame(wkt_step_name="   ", exercise_category=1, exercise_name=2)
        assert fit_decoder.parse_frame_exercise_title(frame) is None

    def test_missing_category_returns_none(self):
        frame = _ExerciseTitleFrame(wkt_step_name="Press", exercise_name=2)
        assert fit_decoder.parse_frame_exercise_title(frame) is None

    def test_missing_exercise_name_returns_none(self):
        frame = _ExerciseTitleFrame(wkt_step_name="Press", exercise_category=1)
        assert fit_decoder.parse_frame_exercise_title(frame) is None

    def test_category_zero_with_name_keeps_zero(self):
        frame = _ExerciseTitleFrame(wkt_step_name="Press", exercise_category=0, exercise_name=7)
        title = fit_decoder.parse_frame_exercise_title(frame)
        assert title.exercise_category == 0
        assert title.exercise_name == 7


class TestParseFrameWorkoutStep:
    """parse_frame_workout_step keeps the FIT exercise codes so the step resolves its exercise title."""

    def test_exercise_name_zero_keeps_zero(self):
        frame = _ExerciseTitleFrame(duration_type="reps", exercise_category=28, exercise_name=0)
        step = fit_decoder.parse_frame_workout_step(frame)
        assert step.exercise_category == 28
        assert step.exercise_name == 0

    def test_missing_exercise_name_is_none(self):
        frame = _ExerciseTitleFrame(duration_type="reps", exercise_category=28)
        assert fit_decoder.parse_frame_workout_step(frame).exercise_name is None


class TestExerciseTitleDecoding:
    """The decoder keeps only the exercise titles that parse to a value."""

    @staticmethod
    def _title(*fields):
        return fit_files.raw_message(_EXERCISE_TITLE, [(0, _UINT16, 1), (1, _UINT16, 2), *fields], local_type=2)

    def test_unnamed_title_frame_is_not_kept(self, tmp_path):
        result = _decode(tmp_path, fit_files.fit_file(self._title(), _session_message()))

        assert result.exercise_titles == ()

    def test_named_title_frame_is_kept(self, tmp_path):
        result = _decode(tmp_path, fit_files.fit_file(self._title((2, _STRING, "Press")), _session_message()))

        assert len(result.exercise_titles) == 1
        assert result.exercise_titles[0].wkt_step_name == "Press"
