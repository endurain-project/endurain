"""The FIT decoder: one FIT file in, one :class:`recording.Recording` out, with no math.

Records become one time-ordered sample table for the file. Each session message becomes a session that owns the
half-open window from its start to the next session's start (the last one to the end of the file); records, laps
and lengths go to the session whose window holds their time. Messages with no time of their own (split summaries,
timeless sets and lengths) belong to the session message that follows them in the file, or to the last session when
none follows. The frame-level readers the decoder needs sit at the top of the module.
"""

import bisect
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict

import fitdecode

import core.exceptions as core_exceptions
import modules.activities.activity.constants as activity_constants
import modules.activities.activity_exercise_titles.contracts as activity_exercise_titles_contracts
import modules.activities.activity_file_import.recording as activity_file_import_recording
import modules.activities.activity_workout_steps.contracts as activity_workout_steps_contracts

#: A FIT enum field decodes to its profile name, or to the raw number when the profile has no name for it.
type FitEnum = str | int


class FitFileId(TypedDict, total=False):
    """A FIT file-id message's fields; all present once the message is read, none for a file without one.

    Attributes:
        type: The file type.
        manufacturer: The device manufacturer.
        product: The device product.
        serial_number: The device serial number.
        time_created: When the file was created.
    """

    type: FitEnum | None
    manufacturer: FitEnum | None
    product: FitEnum | None
    serial_number: int | None
    time_created: datetime | None


def parse_frame_workout(frame: fitdecode.FitDataMessage) -> str:
    """Extract the workout name from a FIT workout frame.

    Args:
        frame: The decoded FIT data message.

    Returns:
        The workout name, or ``Workout`` when absent.
    """
    # Return the extracted name
    return get_value_from_frame(frame, "wkt_name", activity_constants.DEFAULT_ACTIVITY_NAME)


def parse_frame_set(frame: fitdecode.FitDataMessage) -> list[object]:
    """Extract the set fields from a FIT set frame.

    Args:
        frame: The decoded FIT data message.

    Returns:
        The set values as a list, in the parser's field order.
    """
    keys_value = [
        "duration",
        "repetitions",
        "weight",
        "set_type",
        "start_time",
    ]

    keys_raw = [
        "category",
        "category_subtype",
    ]

    set_data = [get_value_from_frame(frame, key) for key in keys_value]
    set_data.extend(get_raw_value_from_frame(frame, key) for key in keys_raw)

    # Adjust category based on category_subtype
    if set_data[5] is None:
        set_data[5] = 0 if set_data[6] is not None else None

    return list(set_data)


def parse_frame_workout_step(
    frame: fitdecode.FitDataMessage,
) -> activity_workout_steps_contracts.ActivityWorkoutStepsCreate:
    """Build a workout step from a FIT workout-step frame.

    Args:
        frame: The decoded FIT data message.

    Returns:
        The workout step.
    """
    keys_value = [
        "message_index",
        "duration_type",
        "duration_value",
        "target_type",
        "target_value",
        "intensity",
        "notes",
        "exercise_weight",
        "weight_display_unit",
    ]

    keys_raw = [
        "exercise_category",
        "exercise_name",
    ]

    workout_set_data = [get_value_from_frame(frame, key) for key in keys_value]
    workout_set_data.extend(get_raw_value_from_frame(frame, key) for key in keys_raw)

    secondary_target_value = None

    if workout_set_data[3] == "swim_stroke":
        if isinstance(workout_set_data[4], str):
            secondary_target_value = workout_set_data[4]
            workout_set_data[4] = None
        elif isinstance(workout_set_data[4], int) and workout_set_data[4] == 255:
            secondary_target_value = "any stroke"
            workout_set_data[4] = None

    if workout_set_data[5] == 7:
        workout_set_data[5] = "active"

    if workout_set_data[9] is None:
        workout_set_data[9] = 0 if workout_set_data[10] is not None else None

    return activity_workout_steps_contracts.ActivityWorkoutStepsCreate(
        message_index=workout_set_data[0] if workout_set_data[0] else 0,
        duration_type=workout_set_data[1],
        duration_value=workout_set_data[2],
        target_type=workout_set_data[3],
        target_value=workout_set_data[4] if workout_set_data[4] else None,
        intensity=workout_set_data[5] if isinstance(workout_set_data[5], str) else None,
        notes=workout_set_data[6],
        exercise_category=workout_set_data[9],
        exercise_name=workout_set_data[10],
        exercise_weight=workout_set_data[7],
        weight_display_unit=workout_set_data[8],
        secondary_target_value=secondary_target_value,
    )


def parse_frame_exercise_title(
    frame: fitdecode.FitDataMessage,
) -> activity_exercise_titles_contracts.ActivityExerciseTitlesCreate | None:
    """Build an exercise title from a FIT exercise-title frame.

    Args:
        frame: The decoded FIT data message.

    Returns:
        The exercise title, or None when the frame has no step name (missing or
        blank) or lacks its exercise category or exercise name code.
    """
    keys_value = [
        "wkt_step_name",
    ]

    keys_raw = [
        "exercise_category",
        "exercise_name",
    ]

    exercise_title_data = [get_value_from_frame(frame, key) for key in keys_value]
    exercise_title_data.extend(get_raw_value_from_frame(frame, key) for key in keys_raw)

    if exercise_title_data[0] is None or not str(exercise_title_data[0]).strip():
        return None
    if exercise_title_data[1] is None or exercise_title_data[2] is None:
        return None

    return activity_exercise_titles_contracts.ActivityExerciseTitlesCreate(
        exercise_category=exercise_title_data[1],
        exercise_name=exercise_title_data[2],
        wkt_step_name=str(exercise_title_data[0]),
    )


def parse_frame_device_settings(frame: fitdecode.FitDataMessage) -> int | None:
    """Extract the time offset from a FIT device-settings frame.

    Args:
        frame: The decoded FIT data message.

    Returns:
        The raw time offset, or None when absent.
    """
    return get_value_from_frame(frame, "time_offset")


# Real UTC offsets span UTC-12:00 to UTC+14:00.
_MIN_UTC_OFFSET_SECONDS = -12 * 3600
_MAX_UTC_OFFSET_SECONDS = 14 * 3600


def parse_frame_activity(frame: fitdecode.FitDataMessage) -> int | None:
    """Extract the device UTC offset from a FIT activity frame.

    The activity message carries ``timestamp`` (UTC) and ``local_timestamp``
    (the same instant as local wall-clock time), both in seconds since the
    FIT epoch. Their difference is the device's UTC offset, available even
    when the file has no GPS fix. Raw values keep the subtraction a plain
    integer operation, independent of the tzinfo fitdecode attaches.

    Args:
        frame: The decoded FIT data message.

    Returns:
        The UTC offset in seconds, or None when either timestamp is absent
        or the offset falls outside the real UTC offset range.
    """
    utc_raw = get_raw_value_from_frame(frame, "timestamp")
    local_raw = get_raw_value_from_frame(frame, "local_timestamp")
    if utc_raw is None or local_raw is None:
        return None
    offset = local_raw - utc_raw
    if not _MIN_UTC_OFFSET_SECONDS <= offset <= _MAX_UTC_OFFSET_SECONDS:
        return None
    return offset


def parse_frame_file_id(frame: fitdecode.FitDataMessage) -> FitFileId:
    """Extract the file identification fields from a FIT file-id frame.

    Args:
        frame: The decoded FIT data message.

    Returns:
        The file-id fields as a dict.
    """
    return {
        "type": get_value_from_frame(frame, "type"),
        "manufacturer": get_value_from_frame(frame, "manufacturer"),
        "product": get_value_from_frame(frame, "product"),
        "serial_number": get_value_from_frame(frame, "serial_number"),
        "time_created": get_value_from_frame(frame, "time_created"),
    }


def interpret_time_offset(raw_offset: int | None) -> int | None:
    """Convert a raw FIT time offset from two's complement to a signed value.

    Args:
        raw_offset: The raw offset, possibly unsigned.

    Returns:
        The signed offset, or the input when it is None or already signed.
    """
    # Check for two's complement representation (values > 2^31)
    if raw_offset != 0 and raw_offset is not None and raw_offset > 2**31 - 1:
        return raw_offset - 2**32
    return raw_offset


def get_value_from_frame(frame: fitdecode.FitDataMessage, key: str | int, default: object = None) -> Any:
    """Read a field's value from a FIT frame.

    fitdecode is untyped and a field's value type is set by the FIT profile at decode time (a scaled number, a
    datetime, an enum name or its raw number, a tuple for array fields), so the value is returned as decoded and
    each caller stores it under the type the profile gives that field.

    Args:
        frame: The decoded FIT data message.
        key: The field name or index.
        default: Value returned when the field is missing.

    Returns:
        The field value, or ``default``.
    """
    try:
        value = frame.get_value(key)
        # Explicit None check so a genuine 0 (e.g. 0 m ascent, 0 W power, a lap
        # that truly covered 0 m) survives instead of collapsing to the default.
        return value if value is not None else default
    except KeyError:
        return default


def get_raw_value_from_frame(frame: fitdecode.FitDataMessage, key: str | int, default: object = None) -> Any:
    """Read a field's raw value from a FIT frame, untyped like ``get_value_from_frame``.

    Args:
        frame: The decoded FIT data message.
        key: The field name or index.
        default: Value returned when the field is missing.

    Returns:
        The raw value, or ``default``.
    """
    try:
        raw_value = frame.get_raw_value(key)
        # Same explicit None check as get_value_from_frame, so a genuine 0 (FIT exercise category 0) survives.
        return raw_value if raw_value is not None else default
    except KeyError:
        return default


def convert_coordinates_to_degrees(
    latitude: float | None, longitude: float | None
) -> tuple[float | None, float | None]:
    """Convert FIT semicircle coordinates to degrees.

    Args:
        latitude: Latitude in semicircles, or None.
        longitude: Longitude in semicircles, or None.

    Returns:
        A (latitude, longitude) tuple; unchanged when either is None.
    """
    # Convert FIT coordinates to degrees if available
    if latitude is not None and longitude is not None:
        latitude = latitude * (180 / 2**31)
        longitude = longitude * (180 / 2**31)

    return latitude, longitude


def resolve_sport(frame: fitdecode.FitDataMessage) -> FitEnum:
    """Resolve the activity type name of a FIT session or lap frame from its sport and sub sport.

    Args:
        frame: The decoded FIT data message.

    Returns:
        The sport name, replaced by the sub sport name where the sub sport is more specific; ``Workout`` when the
        frame names no sport.
    """
    activity_type = get_value_from_frame(frame, "sport", "Workout")
    sub_sport = get_value_from_frame(frame, "sub_sport")
    if sub_sport and sub_sport != "generic":
        if activity_type == "cycling" and sub_sport == "virtual_activity":
            activity_type = "virtual_ride"
        elif activity_type == "cycling" and sub_sport == "commuting":
            activity_type = "commuting_ride"
        elif activity_type == "cycling" and sub_sport == "mixed_surface":
            activity_type = "mixed_surface_ride"
        elif activity_type == "generic" and sub_sport == "breathing":
            activity_type = "hiit"
        elif isinstance(sub_sport, str) and sub_sport.lower() in activity_constants.ACTIVITY_NAME_TO_ID:
            activity_type = sub_sport
    return activity_type


#: The record fields a developer field can stand in for, by the native field number its description names.
_NATIVE_RECORD_CHANNELS = {
    7: "power",
    3: "heart_rate",
    4: "cadence",
    5: "distance",
    6: "speed",
    13: "temperature",
    2: "altitude",
    78: "altitude",
}

#: The global message number of the FIT ``record`` message.
_RECORD_MESG_NUM = 20


def _as_time(value: object) -> datetime | None:
    """Return a decoded FIT time as timezone-aware UTC, or None for anything else.

    fitdecode leaves a time below the FIT datetime minimum (an unset device clock) as a plain integer.

    Args:
        value: The decoded field value.

    Returns:
        The time in UTC, or None when the value is not a datetime.
    """
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _as_name(value: object) -> str | None:
    """Return a decoded enum value as text, or None when absent.

    Args:
        value: The decoded field value.

    Returns:
        The name, or None.
    """
    return None if value is None else str(value)


def _first_present(frame: fitdecode.FitDataMessage, *keys: str) -> Any:
    """Return the first of the fields that has a value.

    Args:
        frame: The decoded FIT data message.
        *keys: The field names, most preferred first.

    Returns:
        The first value present, or None.
    """
    for key in keys:
        value = get_value_from_frame(frame, key)
        if value is not None:
            return value
    return None


def _is_number(value: object) -> bool:
    """Return whether a developer field value is a plain number.

    Args:
        value: The decoded field value.

    Returns:
        True for an int or float that is not a bool.
    """
    return isinstance(value, int | float) and not isinstance(value, bool)


@dataclass(slots=True)
class _SessionEntry:
    """One session message and what is assigned to it while the file is read."""

    start_time: datetime
    sport: str | None
    summary: activity_file_import_recording.DeviceSummary
    laps: list[activity_file_import_recording.Lap] = field(default_factory=list)
    lengths: list[activity_file_import_recording.Length] = field(default_factory=list)
    split_summaries: list[activity_file_import_recording.SplitSummary] = field(default_factory=list)
    sets: list[list[object]] = field(default_factory=list)


class _Untimed[T](TypedDict):
    """An item with no time of its own and how many session messages came before it in the file."""

    after_sessions: int
    item: T


@dataclass(slots=True)
class _FitContent:
    """What one pass over a FIT file collects."""

    limits: activity_file_import_recording.FileLimits = field(default_factory=activity_file_import_recording.FileLimits)
    samples: activity_file_import_recording.SamplesBuilder = field(init=False)
    sessions: list[_SessionEntry] = field(default_factory=list)
    laps: list[activity_file_import_recording.Lap] = field(default_factory=list)
    timed_lengths: list[activity_file_import_recording.Length] = field(default_factory=list)
    untimed_lengths: list[_Untimed[activity_file_import_recording.Length]] = field(default_factory=list)
    split_summaries: list[_Untimed[activity_file_import_recording.SplitSummary]] = field(default_factory=list)
    timed_sets: list[list[object]] = field(default_factory=list)
    untimed_sets: list[_Untimed[list[object]]] = field(default_factory=list)
    workout_steps: list[activity_workout_steps_contracts.ActivityWorkoutStepsCreate] = field(default_factory=list)
    exercise_titles: list[activity_exercise_titles_contracts.ActivityExerciseTitlesCreate] = field(default_factory=list)
    timer_events: list[tuple[datetime, bool]] = field(default_factory=list)
    developer_channels: dict[tuple[int, int], str] = field(default_factory=dict)
    name: str | None = None
    file_id: FitFileId = field(default_factory=FitFileId)
    local_time_offset: int | None = None
    device_time_offset: int | None = None
    multisport: bool = False
    timer_time: float | None = None

    def __post_init__(self) -> None:
        """Start the sample table against the file's limits."""
        self.samples = activity_file_import_recording.SamplesBuilder(self.limits)


def _read_summary(frame: fitdecode.FitDataMessage) -> activity_file_import_recording.DeviceSummary:
    """Read the totals a FIT session message reports.

    Args:
        frame: The decoded FIT session message.

    Returns:
        The device summary, with ``None`` for every field the message leaves out.
    """
    start_lat, start_lon = convert_coordinates_to_degrees(
        get_value_from_frame(frame, "start_position_lat"), get_value_from_frame(frame, "start_position_long")
    )
    return activity_file_import_recording.DeviceSummary(
        total_elapsed_time=get_value_from_frame(frame, "total_elapsed_time"),
        total_timer_time=get_value_from_frame(frame, "total_timer_time"),
        distance=get_value_from_frame(frame, "total_distance"),
        calories=get_value_from_frame(frame, "total_calories"),
        avg_heart_rate=get_value_from_frame(frame, "avg_heart_rate"),
        max_heart_rate=get_value_from_frame(frame, "max_heart_rate"),
        avg_cadence=get_value_from_frame(frame, "avg_cadence"),
        max_cadence=get_value_from_frame(frame, "max_cadence"),
        avg_fractional_cadence=get_value_from_frame(frame, "avg_fractional_cadence"),
        max_fractional_cadence=get_value_from_frame(frame, "max_fractional_cadence"),
        avg_power=get_value_from_frame(frame, "avg_power"),
        max_power=get_value_from_frame(frame, "max_power"),
        normalized_power=get_value_from_frame(frame, "normalized_power"),
        avg_speed=_first_present(frame, "enhanced_avg_speed", "avg_speed"),
        max_speed=_first_present(frame, "enhanced_max_speed", "max_speed"),
        total_ascent=get_value_from_frame(frame, "total_ascent"),
        total_descent=get_value_from_frame(frame, "total_descent"),
        total_cycles=get_value_from_frame(frame, "total_cycles"),
        workout_feeling=get_value_from_frame(frame, "workout_feel"),
        # Polar writes workout_rpe=0 when no RPE was entered; the field is 10-100.
        workout_rpe=get_value_from_frame(frame, "workout_rpe") or None,
        start_lat=start_lat,
        start_lon=start_lon,
    )


def _read_lap(frame: fitdecode.FitDataMessage, start_time: datetime) -> activity_file_import_recording.Lap:
    """Read a FIT lap message.

    Args:
        frame: The decoded FIT lap message.
        start_time: The lap's start time.

    Returns:
        The lap.
    """
    start_lat, start_lon = convert_coordinates_to_degrees(
        get_value_from_frame(frame, "start_position_lat"), get_value_from_frame(frame, "start_position_long")
    )
    end_lat, end_lon = convert_coordinates_to_degrees(
        get_value_from_frame(frame, "end_position_lat"), get_value_from_frame(frame, "end_position_long")
    )
    return activity_file_import_recording.Lap(
        start_time=start_time,
        start_position_lat=start_lat,
        start_position_long=start_lon,
        end_position_lat=end_lat,
        end_position_long=end_lon,
        total_elapsed_time=get_value_from_frame(frame, "total_elapsed_time"),
        total_timer_time=get_value_from_frame(frame, "total_timer_time"),
        total_distance=get_value_from_frame(frame, "total_distance"),
        total_cycles=get_value_from_frame(frame, "total_cycles"),
        total_calories=get_value_from_frame(frame, "total_calories"),
        avg_heart_rate=get_value_from_frame(frame, "avg_heart_rate"),
        max_heart_rate=get_value_from_frame(frame, "max_heart_rate"),
        avg_cadence=get_value_from_frame(frame, "avg_cadence"),
        max_cadence=get_value_from_frame(frame, "max_cadence"),
        avg_fractional_cadence=get_value_from_frame(frame, "avg_fractional_cadence"),
        max_fractional_cadence=get_value_from_frame(frame, "max_fractional_cadence"),
        avg_power=get_value_from_frame(frame, "avg_power"),
        max_power=get_value_from_frame(frame, "max_power"),
        normalized_power=get_value_from_frame(frame, "normalized_power"),
        total_work=get_value_from_frame(frame, "total_work"),
        total_ascent=get_value_from_frame(frame, "total_ascent"),
        total_descent=get_value_from_frame(frame, "total_descent"),
        avg_speed=_first_present(frame, "enhanced_avg_speed", "avg_speed"),
        max_speed=_first_present(frame, "enhanced_max_speed", "max_speed"),
        min_altitude=get_value_from_frame(frame, "enhanced_min_altitude"),
        max_altitude=get_value_from_frame(frame, "enhanced_max_altitude"),
        intensity=_as_name(get_value_from_frame(frame, "intensity")),
        lap_trigger=_as_name(get_value_from_frame(frame, "lap_trigger")),
        sport=_as_name(get_value_from_frame(frame, "sport")),
        sub_sport=_as_name(get_value_from_frame(frame, "sub_sport")),
        avg_vertical_oscillation=get_value_from_frame(frame, "avg_vertical_oscillation"),
        avg_stance_time=get_value_from_frame(frame, "avg_stance_time"),
        avg_vertical_ratio=get_value_from_frame(frame, "avg_vertical_ratio"),
        avg_step_length=get_value_from_frame(frame, "avg_step_length"),
    )


def _read_length(frame: fitdecode.FitDataMessage) -> activity_file_import_recording.Length:
    """Read a FIT pool-length message.

    Args:
        frame: The decoded FIT length message.

    Returns:
        The length; a field the message leaves out or writes as an invalid value is ``None``.
    """
    timer_time = get_value_from_frame(frame, "total_timer_time")
    return activity_file_import_recording.Length(
        message_index=get_value_from_frame(frame, "message_index"),
        start_time=_as_time(get_value_from_frame(frame, "start_time")),
        total_elapsed_time=get_value_from_frame(frame, "total_elapsed_time"),
        total_timer_time=timer_time if _is_number(timer_time) else None,
        total_strokes=get_value_from_frame(frame, "total_strokes"),
        avg_speed=get_value_from_frame(frame, "avg_speed"),
        swim_stroke=_as_name(get_value_from_frame(frame, "swim_stroke")),
        avg_swimming_cadence=get_value_from_frame(frame, "avg_swimming_cadence"),
        length_type=_as_name(get_value_from_frame(frame, "length_type")),
    )


def _read_record(frame: fitdecode.FitDataMessage, content: _FitContent) -> None:
    """Append a FIT record message to the sample table; a record with no usable timestamp is skipped.

    Args:
        frame: The decoded FIT record message.
        content: What the file has yielded so far.
    """
    time = _as_time(get_value_from_frame(frame, "timestamp"))
    if time is None:
        return
    lat, lon = convert_coordinates_to_degrees(
        get_value_from_frame(frame, "position_lat"), get_value_from_frame(frame, "position_long")
    )
    if lat is None or lon is None:
        lat = lon = None
    cadence = get_value_from_frame(frame, "cadence")
    if cadence is not None:
        cadence = float(cadence) + (get_value_from_frame(frame, "fractional_cadence") or 0)
    channels: dict[str, Any] = {
        "altitude": get_value_from_frame(frame, "enhanced_altitude"),
        "distance": get_value_from_frame(frame, "distance"),
        "speed": _first_present(frame, "enhanced_speed", "speed"),
        "heart_rate": get_value_from_frame(frame, "heart_rate"),
        "cadence": cadence,
        "power": get_value_from_frame(frame, "power"),
        "temperature": get_value_from_frame(frame, "temperature"),
    }
    for data in frame.fields:
        if data.field_type != "devfield":
            continue
        channel = content.developer_channels.get((data.field.dev_data_index, data.field.def_num))
        if channel is not None and channels[channel] is None and _is_number(data.value):
            channels[channel] = float(data.value) if channel in {"cadence"} else data.value
    for channel in ("heart_rate", "power"):
        if channels[channel] is not None:
            channels[channel] = int(channels[channel])
    if channels["temperature"] is not None:
        channels["temperature"] = float(channels["temperature"])
    content.samples.append(time, lat=lat, lon=lon, **channels)


def _read_field_description(frame: fitdecode.FitDataMessage, content: _FitContent) -> None:
    """Remember which record channel a developer field fills.

    Args:
        frame: The decoded FIT field-description message.
        content: What the file has yielded so far.
    """
    if get_raw_value_from_frame(frame, "native_mesg_num") != _RECORD_MESG_NUM:
        return
    channel = _NATIVE_RECORD_CHANNELS.get(get_raw_value_from_frame(frame, "native_field_num"))
    index = get_raw_value_from_frame(frame, "developer_data_index")
    number = get_raw_value_from_frame(frame, "field_definition_number")
    if channel is not None and index is not None and number is not None:
        content.developer_channels[(index, number)] = channel


def _read_message(frame: fitdecode.FitDataMessage, content: _FitContent) -> None:
    """Route one FIT data message into what the file yields.

    Args:
        frame: The decoded FIT data message.
        content: What the file has yielded so far.

    Raises:
        InvalidInputError: When a session has no start time or the file passes a limit.
    """
    name = frame.name
    if name == "record":
        _read_record(frame, content)
    elif name == "session":
        start_time = _as_time(get_value_from_frame(frame, "start_time"))
        if start_time is None:
            raise core_exceptions.InvalidInputError("A FIT session has no start time")
        content.limits.count_session()
        content.sessions.append(
            _SessionEntry(
                start_time=start_time,
                sport=_as_name(resolve_sport(frame)),
                summary=_read_summary(frame),
            )
        )
    elif name == "lap":
        start_time = _as_time(get_value_from_frame(frame, "start_time"))
        if start_time is not None:
            content.laps.append(_read_lap(frame, start_time))
    elif name == "length":
        length = _read_length(frame)
        if length.start_time is None:
            content.untimed_lengths.append({"after_sessions": len(content.sessions), "item": length})
        else:
            content.timed_lengths.append(length)
    elif name in {"split_summary", "unknown_313"}:
        content.split_summaries.append(
            {
                "after_sessions": len(content.sessions),
                "item": activity_file_import_recording.SplitSummary(
                    split_type=_as_name(get_value_from_frame(frame, "split_type")),
                    total_timer_time=get_value_from_frame(frame, "total_timer_time"),
                ),
            }
        )
    elif name == "set":
        set_data = parse_frame_set(frame)
        if _as_time(set_data[4]) is None:
            content.untimed_sets.append({"after_sessions": len(content.sessions), "item": set_data})
        else:
            content.timed_sets.append(set_data)
    elif name == "workout_step":
        content.workout_steps.append(parse_frame_workout_step(frame))
    elif name == "exercise_title":
        title = parse_frame_exercise_title(frame)
        if title is not None:
            content.exercise_titles.append(title)
    elif name == "event":
        _read_timer_event(frame, content)
    elif name == "workout":
        workout_name = get_value_from_frame(frame, "wkt_name")
        content.name = (
            workout_name if workout_name and workout_name != activity_constants.DEFAULT_ACTIVITY_NAME else None
        )
    elif name == "field_description":
        _read_field_description(frame, content)
    elif name == "file_id":
        content.file_id = parse_frame_file_id(frame)
    elif name == "activity":
        content.local_time_offset = parse_frame_activity(frame)
        content.multisport = get_value_from_frame(frame, "type") == "auto_multi_sport"
        content.timer_time = get_value_from_frame(frame, "total_timer_time")
    elif name == "device_settings":
        content.device_time_offset = interpret_time_offset(parse_frame_device_settings(frame))


def _read_timer_event(frame: fitdecode.FitDataMessage, content: _FitContent) -> None:
    """Remember a timer start or stop event.

    Args:
        frame: The decoded FIT event message.
        content: What the file has yielded so far.
    """
    if get_value_from_frame(frame, "event") != "timer":
        return
    time = _as_time(get_value_from_frame(frame, "timestamp"))
    event_type = get_value_from_frame(frame, "event_type")
    if time is None:
        return
    if event_type in {"stop_all", "stop"}:
        content.timer_events.append((time, True))
    elif event_type == "start":
        content.timer_events.append((time, False))


def _pauses(
    events: list[tuple[datetime, bool]], starts: list[datetime]
) -> list[list[activity_file_import_recording.Pause]]:
    """Pair the timer stops with the starts that follow them, inside each session's window.

    Args:
        events: The timer events as (time, is_stop), in time order.
        starts: The session start times in time order.

    Returns:
        The pauses of each session; a stop with no later start in its window is not a pause.
    """
    pauses: list[list[activity_file_import_recording.Pause]] = [[] for _ in starts]
    pending: list[datetime | None] = [None for _ in starts]
    for time, is_stop in events:
        owner = _owner(starts, time)
        if is_stop:
            if pending[owner] is None:
                pending[owner] = time
        elif (stopped := pending[owner]) is not None:
            pauses[owner].append(activity_file_import_recording.Pause(start=stopped, end=time))
            pending[owner] = None
    return pauses


def _owner(starts: list[datetime], time: datetime) -> int:
    """Return the index of the session whose window holds a time.

    Args:
        starts: The session start times in time order.
        time: The instant to place; one before the first start goes to the first session.

    Returns:
        The session index.
    """
    return max(bisect.bisect_right(starts, time) - 1, 0)


def _file_order_owner(after_sessions: int, session_count: int) -> int:
    """Return the file-order index of the session an untimed message belongs to.

    Args:
        after_sessions: How many session messages came before the message.
        session_count: The number of session messages in the file.

    Returns:
        The first session message after it, or the last session when none follows.
    """
    return min(after_sessions, session_count - 1)


def _window_end(entry: _SessionEntry, next_start: datetime | None) -> tuple[datetime | None, bool]:
    """Return where a session's records end, and whether a record on that instant is still the session's.

    A session runs to its own end (start plus elapsed time, inclusive): records the device wrote after it ended
    belong to no session. A next session starting sooner cuts it at that start, exclusive. A session without an
    elapsed time runs to the next start, or to the end of the file.

    Args:
        entry: The session.
        next_start: When the next session starts, ``None`` for the last one.

    Returns:
        The end instant (``None`` for the end of the file) and whether it is inclusive.
    """
    elapsed = entry.summary.total_elapsed_time
    own_end = None if elapsed is None else entry.start_time + timedelta(seconds=elapsed)
    if own_end is not None and (next_start is None or own_end < next_start):
        return own_end, True
    return next_start, False


def _build_sessions(
    content: _FitContent, samples: activity_file_import_recording.Samples
) -> tuple[activity_file_import_recording.Session, ...]:
    """Cut the file's data into one session per session message.

    Args:
        content: What the file has yielded.
        samples: The file's time-ordered sample table.

    Returns:
        The sessions, in time order.
    """
    entries = content.sessions
    file_order = sorted(range(len(entries)), key=lambda i: entries[i].start_time)
    position = {file_index: time_index for time_index, file_index in enumerate(file_order)}
    ordered = [entries[i] for i in file_order]
    starts = [entry.start_time for entry in ordered]

    for lap in content.laps:
        ordered[_owner(starts, lap.start_time)].laps.append(lap)
    for length in content.timed_lengths:
        if length.start_time is not None:
            ordered[_owner(starts, length.start_time)].lengths.append(length)
    for set_data in content.timed_sets:
        set_time = _as_time(set_data[4])
        if set_time is not None:
            ordered[_owner(starts, set_time)].sets.append(set_data)
    for untimed_length in content.untimed_lengths:
        owner = position[_file_order_owner(untimed_length["after_sessions"], len(entries))]
        ordered[owner].lengths.append(untimed_length["item"])
    for summary in content.split_summaries:
        owner = position[_file_order_owner(summary["after_sessions"], len(entries))]
        ordered[owner].split_summaries.append(summary["item"])
    for untimed_set in content.untimed_sets:
        owner = position[_file_order_owner(untimed_set["after_sessions"], len(entries))]
        ordered[owner].sets.append(untimed_set["item"])

    pauses = _pauses(sorted(content.timer_events, key=lambda event: event[0]), starts)
    sessions = []
    for index, entry in enumerate(ordered):
        end, end_inclusive = _window_end(entry, starts[index + 1] if index + 1 < len(starts) else None)
        sessions.append(
            activity_file_import_recording.Session(
                sport=entry.sport,
                start_time=entry.start_time,
                samples=activity_file_import_recording.samples_between(
                    samples, starts[index], end, end_inclusive=end_inclusive
                ),
                pauses=tuple(pauses[index]),
                laps=tuple(entry.laps),
                lengths=tuple(entry.lengths),
                split_summaries=tuple(entry.split_summaries),
                sets=tuple(entry.sets),
                workout_steps=tuple(content.workout_steps) if index == 0 else (),
                summary=entry.summary,
            )
        )
    return tuple(sessions)


def decode_fit(path: str) -> activity_file_import_recording.Recording:
    """Decode a FIT file into a recording, with no math.

    Args:
        path: Path of the FIT file.

    Returns:
        The recording; one session per FIT session message, in time order.

    Raises:
        InvalidInputError: When the file is not a readable FIT file, holds records but no session, has a session with
            no start time, or passes the sample or session limit.
        ProcessingError: When the file cannot be read.
    """
    content = _FitContent()
    try:
        with open(path, "rb") as fit_file:
            for frame in fitdecode.FitReader(fit_file):
                if isinstance(frame, fitdecode.FitDataMessage):
                    _read_message(frame, content)
    except (fitdecode.FitError, TypeError) as err:
        # The uploader's file is the problem (fitdecode raises TypeError for a field size its type cannot hold), so a
        # retry reaches the same verdict.
        raise core_exceptions.InvalidInputError("Can't parse FIT file") from err
    except OSError as err:
        raise core_exceptions.ProcessingError("Can't read FIT file") from err

    samples = content.samples.build()
    if not content.sessions and len(samples):
        raise core_exceptions.InvalidInputError("The FIT file has no session")
    manufacturer = content.file_id.get("manufacturer")
    product = content.file_id.get("product")
    return activity_file_import_recording.Recording(
        format="fit",
        sessions=_build_sessions(content, samples) if content.sessions else (),
        name=content.name,
        manufacturer=None if manufacturer is None else str(manufacturer),
        product=None if product is None else str(product),
        local_time_offset=content.local_time_offset,
        device_time_offset=content.device_time_offset,
        multisport=content.multisport,
        timer_time=content.timer_time,
        exercise_titles=tuple(content.exercise_titles),
    )
