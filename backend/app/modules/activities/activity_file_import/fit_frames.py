"""Per-message extraction for the FIT format: one frame in, plain data out.

The leaf half of the FIT parser. Each ``parse_frame_*`` reads a single FIT data
message and returns a dict or primitive; none of them touches parse state, calls
another frame parser, or knows an activity exists. ``fit_parser`` holds the other
half — the dispatch that routes each message to one of these and accumulates the
result into an activity.

Split out because the two answer different questions ("what does a lap message
contain?" against "how do these messages become an activity?") and the file had
grown to 1278 lines holding both. The dependency is one-way by construction: the
dispatch imports these, and nothing here imports back.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, NotRequired, TypedDict
from zoneinfo import ZoneInfo, available_timezones

import fitdecode

import core.logger as core_logger
import modules.activities.activity.constants as activity_constants
import modules.activities.activity_exercise_titles.contracts as activity_exercise_titles_contracts
import modules.activities.activity_workout_steps.contracts as activity_workout_steps_contracts

logger = core_logger.get_logger(__name__)

#: A FIT enum field decodes to its profile name, or to the raw number when the profile has no name for it.
type FitEnum = str | int

#: The session summary fields, in the order ``parse_frame_session`` returns them: start latitude and longitude,
#: activity type, start time, elapsed and timer seconds, calories, distance, average and maximum heart rate,
#: cadence and power, ascent, descent, normalized power, average and maximum speed, workout feel, RPE and cycles.
type FitSessionFields = tuple[
    float | None,
    float | None,
    FitEnum,
    datetime,
    float,
    float,
    int | None,
    float | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    float | None,
    float | None,
    int | None,
    int | None,
    int | None,
]

#: One record sample: latitude, longitude, elevation, time, heart rate, cadence, power and temperature.
type FitRecordFields = tuple[
    float | None,
    float | None,
    float | None,
    datetime,
    int | None,
    int | None,
    int | None,
    int | None,
]

#: The split fields, in the order ``parse_frame_split`` returns them: split type, elapsed and timer seconds,
#: distance, average speed, start time, ascent, descent, start and end position (semicircles), maximum speed,
#: end time, calories and start elevation.
type FitSplitFields = tuple[
    FitEnum | None,
    float | None,
    float | None,
    float | None,
    float | None,
    datetime | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    int | None,
    float | None,
    datetime | None,
    int | None,
    float | None,
]


class FitLap(TypedDict):
    """A FIT lap message's fields, the coordinates in degrees.

    The keys are the stored lap's columns. ``enhanced_avg_pace`` and ``enhanced_max_pace`` are present only when
    the lap has the matching speed.
    """

    start_time: datetime | None
    start_position_lat: float | None
    start_position_long: float | None
    end_position_lat: float | None
    end_position_long: float | None
    total_elapsed_time: float | None
    total_timer_time: float | None
    total_distance: float | None
    total_cycles: int | None
    total_calories: int | None
    avg_heart_rate: int | None
    max_heart_rate: int | None
    avg_cadence: int | None
    max_cadence: int | None
    avg_power: int | None
    max_power: int | None
    total_ascent: int | None
    total_descent: int | None
    intensity: FitEnum | None
    lap_trigger: FitEnum | None
    sport: FitEnum | None
    sub_sport: FitEnum | None
    normalized_power: int | None
    total_work: int | None
    avg_vertical_oscillation: float | None
    avg_stance_time: float | None
    avg_fractional_cadence: float | None
    max_fractional_cadence: float | None
    enhanced_avg_speed: float | None
    enhanced_max_speed: float | None
    enhanced_min_altitude: float | None
    enhanced_max_altitude: float | None
    avg_vertical_ratio: float | None
    avg_step_length: float | None
    enhanced_avg_pace: NotRequired[float]
    enhanced_max_pace: NotRequired[float]


class FitSplitSummary(TypedDict):
    """A FIT split-summary message's fields.

    Attributes:
        split_type: The split type.
        total_timer_time: Working seconds, or None when the message carries none.
    """

    split_type: FitEnum | None
    total_timer_time: float | None


class FitLength(TypedDict):
    """A FIT pool-length message's fields.

    Attributes:
        message_index: Index of the length in the file.
        start_time: When the length started.
        total_elapsed_time: Elapsed seconds.
        total_timer_time: Timer seconds.
        total_strokes: Strokes.
        avg_speed: Average speed in m/s.
        swim_stroke: The stroke.
        avg_swimming_cadence: Average cadence in strokes per minute.
        length_type: ``active`` or ``idle``.
    """

    message_index: int | None
    start_time: datetime | None
    total_elapsed_time: float | None
    total_timer_time: float
    total_strokes: int | None
    avg_speed: float | None
    swim_stroke: FitEnum | None
    avg_swimming_cadence: int | None
    length_type: FitEnum | None


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


class FitMonitoringSteps(TypedDict):
    """A step sample of a FIT monitoring message.

    Attributes:
        steps: Steps.
        active_time: Active seconds.
        active_calories: Active calories.
        current_activity_type_intensity: The packed activity type and intensity.
        activity_type: The activity type.
        intensity: The intensity.
        distance: Distance in meters.
        duration_min: Duration in minutes.
        timestamp: When the sample was taken, UTC.
    """

    steps: int | None
    active_time: float | None
    active_calories: int | None
    current_activity_type_intensity: int | None
    activity_type: FitEnum | None
    intensity: int | None
    distance: float | None
    duration_min: int | None
    timestamp: datetime


class FitMonitoringHeartRate(TypedDict):
    """A heart-rate sample of a FIT monitoring message.

    Attributes:
        heart_rate: Heart rate in bpm.
        timestamp: When the sample was taken, UTC.
    """

    heart_rate: int | None
    timestamp: datetime


class FitRestingHeartRate(TypedDict):
    """A FIT monitoring heart-rate-data message's fields.

    Attributes:
        timestamp: When the message was recorded.
        resting_heart_rate: Resting heart rate in bpm.
        current_day_resting_heart_rate: The day's resting heart rate in bpm.
    """

    timestamp: datetime | None
    resting_heart_rate: int | None
    current_day_resting_heart_rate: int | None


def parse_frame_session(frame: fitdecode.FitDataMessage) -> FitSessionFields:
    """Extract the session summary fields from a FIT session frame.

    Args:
        frame: The decoded FIT data message.

    Returns:
        The session fields as an ordered tuple.
    """
    # Extracting coordinates
    initial_latitude, initial_longitude = convert_coordinates_to_degrees(
        get_value_from_frame(frame, "start_position_lat"),
        get_value_from_frame(frame, "start_position_long"),
    )

    # Activity type logic
    activity_type = get_value_from_frame(frame, "sport", "Workout")
    sub_sport = get_value_from_frame(frame, "sub_sport")
    if sub_sport and sub_sport != "generic":
        if activity_type == "cycling" and sub_sport == "virtual_activity":
            activity_type = "virtual_ride"
        elif activity_type == "cycling" and sub_sport == "commuting":
            activity_type = "commuting_ride"
        elif activity_type == "cycling" and sub_sport == "mixed_surface":
            activity_type = "mixed_surface_ride"
        elif (activity_type == "generic" and sub_sport == "breathing") or activity_type == 62:
            activity_type = "hiit"
        elif activity_type == 64 and sub_sport == 85:
            activity_type = "padel"
        elif isinstance(sub_sport, str) and sub_sport.lower() in activity_constants.ACTIVITY_NAME_TO_ID:
            activity_type = sub_sport

    # Extracting time values
    start_time = get_value_from_frame(frame, "start_time")
    total_elapsed_time = get_value_from_frame(frame, "total_elapsed_time")
    total_timer_time = get_value_from_frame(frame, "total_timer_time")

    # Extracting other values
    return (
        initial_latitude,
        initial_longitude,
        activity_type,
        start_time,
        total_elapsed_time,
        total_timer_time,
        get_value_from_frame(frame, "total_calories"),
        get_value_from_frame(frame, "total_distance"),
        get_value_from_frame(frame, "avg_heart_rate"),
        get_value_from_frame(frame, "max_heart_rate"),
        get_value_from_frame(frame, "avg_cadence"),
        get_value_from_frame(frame, "max_cadence"),
        get_value_from_frame(frame, "avg_power"),
        get_value_from_frame(frame, "max_power"),
        get_value_from_frame(frame, "total_ascent"),
        get_value_from_frame(frame, "total_descent"),
        get_value_from_frame(frame, "normalized_power"),
        # Prefer the enhanced speed fields, falling back to the legacy
        # avg_speed/max_speed fields some devices write instead.
        get_value_from_frame(frame, "enhanced_avg_speed", get_value_from_frame(frame, "avg_speed")),
        get_value_from_frame(frame, "enhanced_max_speed", get_value_from_frame(frame, "max_speed")),
        get_value_from_frame(frame, "workout_feel"),
        # Polar writes workout_rpe=0 when no RPE was entered; the field is 10-100.
        get_value_from_frame(frame, "workout_rpe") or None,
        get_value_from_frame(frame, "total_cycles"),
    )


def parse_frame_workout(frame: fitdecode.FitDataMessage) -> str:
    """Extract the workout name from a FIT workout frame.

    Args:
        frame: The decoded FIT data message.

    Returns:
        The workout name, or ``Workout`` when absent.
    """
    # Return the extracted name
    return get_value_from_frame(frame, "wkt_name", activity_constants.DEFAULT_ACTIVITY_NAME)


def parse_frame_record(frame: fitdecode.FitDataMessage) -> FitRecordFields:
    """Extract the sample fields from a FIT record frame.

    Args:
        frame: The decoded FIT data message.

    Returns:
        A tuple of latitude, longitude, elevation, time, heart rate, cadence, power and temperature.
    """
    # Extracting data using the helper function
    latitude = get_value_from_frame(frame, "position_lat")
    longitude = get_value_from_frame(frame, "position_long")
    elevation = get_value_from_frame(frame, "enhanced_altitude")
    time = get_value_from_frame(frame, "timestamp")
    heart_rate = get_value_from_frame(frame, "heart_rate")
    cadence = get_value_from_frame(frame, "cadence")
    power = get_value_from_frame(frame, "power")
    temperature = get_value_from_frame(frame, "temperature")

    latitude, longitude = convert_coordinates_to_degrees(latitude, longitude)

    # Return all extracted values
    return latitude, longitude, elevation, time, heart_rate, cadence, power, temperature


def parse_frame_lap(frame: fitdecode.FitDataMessage) -> FitLap:
    """Extract the lap fields from a FIT lap frame.

    Args:
        frame: The decoded FIT data message.

    Returns:
        The lap fields as a dict.
    """
    lap_dict: FitLap = {
        "start_time": get_value_from_frame(frame, "start_time"),
        "start_position_lat": get_value_from_frame(frame, "start_position_lat"),
        "start_position_long": get_value_from_frame(frame, "start_position_long"),
        "end_position_lat": get_value_from_frame(frame, "end_position_lat"),
        "end_position_long": get_value_from_frame(frame, "end_position_long"),
        "total_elapsed_time": get_value_from_frame(frame, "total_elapsed_time"),
        "total_timer_time": get_value_from_frame(frame, "total_timer_time"),
        "total_distance": get_value_from_frame(frame, "total_distance"),
        "total_cycles": get_value_from_frame(frame, "total_cycles"),
        "total_calories": get_value_from_frame(frame, "total_calories"),
        "avg_heart_rate": get_value_from_frame(frame, "avg_heart_rate"),
        "max_heart_rate": get_value_from_frame(frame, "max_heart_rate"),
        "avg_cadence": get_value_from_frame(frame, "avg_cadence"),
        "max_cadence": get_value_from_frame(frame, "max_cadence"),
        "avg_power": get_value_from_frame(frame, "avg_power"),
        "max_power": get_value_from_frame(frame, "max_power"),
        "total_ascent": get_value_from_frame(frame, "total_ascent"),
        "total_descent": get_value_from_frame(frame, "total_descent"),
        "intensity": get_value_from_frame(frame, "intensity"),
        "lap_trigger": get_value_from_frame(frame, "lap_trigger"),
        "sport": get_value_from_frame(frame, "sport"),
        "sub_sport": get_value_from_frame(frame, "sub_sport"),
        "normalized_power": get_value_from_frame(frame, "normalized_power"),
        "total_work": get_value_from_frame(frame, "total_work"),
        "avg_vertical_oscillation": get_value_from_frame(frame, "avg_vertical_oscillation"),
        "avg_stance_time": get_value_from_frame(frame, "avg_stance_time"),
        "avg_fractional_cadence": get_value_from_frame(frame, "avg_fractional_cadence"),
        "max_fractional_cadence": get_value_from_frame(frame, "max_fractional_cadence"),
        "enhanced_avg_speed": get_value_from_frame(frame, "enhanced_avg_speed"),
        "enhanced_max_speed": get_value_from_frame(frame, "enhanced_max_speed"),
        "enhanced_min_altitude": get_value_from_frame(frame, "enhanced_min_altitude"),
        "enhanced_max_altitude": get_value_from_frame(frame, "enhanced_max_altitude"),
        "avg_vertical_ratio": get_value_from_frame(frame, "avg_vertical_ratio"),
        "avg_step_length": get_value_from_frame(frame, "avg_step_length"),
    }

    (
        lap_dict["start_position_lat"],
        lap_dict["start_position_long"],
    ) = convert_coordinates_to_degrees(
        lap_dict["start_position_lat"],
        lap_dict["start_position_long"],
    )
    lap_dict["end_position_lat"], lap_dict["end_position_long"] = convert_coordinates_to_degrees(
        lap_dict["end_position_lat"],
        lap_dict["end_position_long"],
    )

    # Prefer the enhanced speed fields; fall back to the legacy avg_speed/max_speed
    # some devices write on laps, mirroring parse_frame_session. When no speed is
    # recorded at all, derive average speed from distance/time so pace still shows.
    #
    # These use a truthy check (not `is None`) on purpose: a 0 m/s speed carries no
    # meaningful pace and would break the `1 / speed` inversions below, so a real 0
    # is treated like a missing value here. This deliberately differs from the
    # "preserve real zeros" (`is None`) handling in get_value_from_frame, where a 0
    # is a legitimate reading worth keeping.
    if not lap_dict["enhanced_avg_speed"]:
        lap_dict["enhanced_avg_speed"] = get_value_from_frame(frame, "avg_speed")
    if not lap_dict["enhanced_max_speed"]:
        lap_dict["enhanced_max_speed"] = get_value_from_frame(frame, "max_speed")

    if not lap_dict["enhanced_avg_speed"] and lap_dict["total_distance"] and lap_dict["total_timer_time"]:
        lap_dict["enhanced_avg_speed"] = lap_dict["total_distance"] / lap_dict["total_timer_time"]

    if lap_dict["enhanced_avg_speed"]:
        lap_dict["enhanced_avg_pace"] = 1 / lap_dict["enhanced_avg_speed"]

    if lap_dict["enhanced_max_speed"]:
        lap_dict["enhanced_max_pace"] = 1 / lap_dict["enhanced_max_speed"]

    return lap_dict


def parse_frame_split(frame: fitdecode.FitDataMessage) -> FitSplitFields:
    """Extract the split fields from a FIT split frame.

    Args:
        frame: The decoded FIT data message.

    Returns:
        The split values as a tuple, in the parser's field order.
    """
    # Define a list of keys and their default values
    keys_defaults = [
        ("split_type", 0),
        ("total_elapsed_time", 1),
        ("total_timer_time", 2),
        ("total_distance", 3),
        ("avg_speed", 4),
        ("start_time", 9),
        ("total_ascent", 13),
        ("total_descent", 14),
        ("start_position_lat", 21),
        ("start_position_long", 22),
        ("end_position_lat", 23),
        ("end_position_long", 24),
        ("max_speed", 25),
        ("end_time", 27),
        ("total_calories", 28),
        ("start_elevation", 74),
    ]

    # Extract values using the keys and defaults
    values = [get_value_from_frame(frame, key, get_value_from_frame(frame, default)) for key, default in keys_defaults]

    return tuple(values)


def parse_frame_split_summary(frame: fitdecode.FitDataMessage) -> tuple[FitEnum | None, float | None]:
    """Extract the split type and working time from a FIT split-summary frame.

    Args:
        frame: The decoded FIT data message.

    Returns:
        A tuple of split type and total timer time.
    """
    # split type
    split_type = get_value_from_frame(frame, "split_type")
    if split_type is None:
        split_type = get_value_from_frame(frame, 0)
    # total working time
    total_timer_time = get_value_from_frame(frame, "total_timer_time")
    if total_timer_time is None:
        total_timer_time = get_value_from_frame(frame, 4)
        if total_timer_time is not None:
            total_timer_time = total_timer_time / 1000

    return split_type, total_timer_time


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


def parse_frame_length(frame: fitdecode.FitDataMessage) -> FitLength:
    """Extract the pool-length fields from a FIT length frame.

    Args:
        frame: The decoded FIT data message.

    Returns:
        The length fields as a dict.
    """
    return {
        "message_index": get_value_from_frame(frame, "message_index"),
        "start_time": get_value_from_frame(frame, "start_time"),
        "total_elapsed_time": get_value_from_frame(frame, "total_elapsed_time"),
        "total_timer_time": get_value_from_frame(frame, "total_timer_time"),
        "total_strokes": get_value_from_frame(frame, "total_strokes"),
        "avg_speed": get_value_from_frame(frame, "avg_speed"),
        "swim_stroke": get_value_from_frame(frame, "swim_stroke"),
        "avg_swimming_cadence": get_value_from_frame(frame, "avg_swimming_cadence"),
        "length_type": get_value_from_frame(frame, "length_type"),
    }


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


def parse_frame_monitoring(
    frame: fitdecode.FitDataMessage,
    last_timestamp: int,
) -> tuple[list[FitMonitoringSteps], list[FitMonitoringHeartRate]]:
    """Extract step and heart-rate samples from a FIT monitoring frame.

    Args:
        frame: The decoded FIT data message.
        last_timestamp: Timestamp of the previous monitoring frame.

    Returns:
        A tuple of step samples and heart-rate samples.
    """
    steps: list[FitMonitoringSteps] = []
    heart_rate: list[FitMonitoringHeartRate] = []

    # Field name -> decoded value, subfields included; the fields a frame carries vary by device.
    data: dict[str, Any] = {}
    for frame_field in frame.fields:
        data.update({frame_field.name: frame_field.value})
        for sf in getattr(frame_field.field, "subfields", []) or []:
            data.update({sf.name: sf.render(frame_field.raw_value)})

    # Reconstruct timestamp with timestamp_16.
    current_timestamp = None
    if data.get("timestamp_16") is not None:
        current_timestamp = (last_timestamp & 0xFFFF0000) | data["timestamp_16"]
        if current_timestamp < last_timestamp:
            current_timestamp += 0x10000
    else:
        current_timestamp = last_timestamp

    timestamp = datetime.fromtimestamp(
        current_timestamp + fitdecode.FIT_UTC_REFERENCE,
        tz=UTC,
    )

    if data.get("steps"):
        steps.append(
            {
                "steps": data.get("steps"),
                "active_time": data.get("active_time"),
                "active_calories": data.get("active_calories"),
                "current_activity_type_intensity": data.get("current_activity_type_intensity"),
                "activity_type": data.get("activity_type"),
                "intensity": data.get("intensity"),
                "distance": data.get("distance"),
                "duration_min": data.get("duration_min"),
                "timestamp": timestamp,
            }
        )

    if data.get("heart_rate"):
        heart_rate.append(
            {
                "heart_rate": data.get("heart_rate"),
                "timestamp": timestamp,
            }
        )

    return steps, heart_rate


def parse_frame_monitoring_hr_data(frame: fitdecode.FitDataMessage) -> FitRestingHeartRate:
    """Extract the resting heart-rate fields from a FIT monitoring frame.

    Args:
        frame: The decoded FIT data message.

    Returns:
        The timestamp and resting heart-rate fields as a dict.
    """
    return {
        "timestamp": get_value_from_frame(frame, "timestamp"),
        "resting_heart_rate": get_value_from_frame(frame, "resting_heart_rate"),
        "current_day_resting_heart_rate": get_value_from_frame(frame, "current_day_resting_heart_rate"),
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


def calculate_pace(
    distance: float | None,
    total_timer_time: float,
    activity_type: FitEnum | None,
    split_summary: Sequence[FitSplitSummary],
    lengths: Sequence[FitLength],
) -> tuple[float, float]:
    """Compute the active time and pace for an activity.

    Args:
        distance: Total distance, or None when unknown.
        total_timer_time: Total timer time.
        activity_type: Activity type code to filter by, or None.
        split_summary: Parsed split-summary records.
        lengths: Parsed pool-length records.

    Returns:
        A tuple of active time and pace.
    """
    if distance:
        if activity_type != "lap_swimming" or (activity_type == "lap_swimming" and not split_summary and not lengths):
            return total_timer_time, total_timer_time / distance
        if activity_type == "lap_swimming" and lengths:
            # Swimming pace calculation based on lengths
            time_active: float = 0
            for length in lengths:
                if length["length_type"] == "active":
                    time_active += length["total_timer_time"]

            return time_active, time_active / distance
        # Swimming pace calculation based on split summary
        time_active = 0
        for split in split_summary:
            # A rest split, or a summary without a timer time, has no working seconds to add.
            split_timer_time = split["total_timer_time"]
            if split["split_type"] != "interval_rest" and split_timer_time is not None:
                time_active += split_timer_time

        return time_active, time_active / distance
    return total_timer_time, 0


def _timezone_from_offset(
    offset_seconds: int,
    reference_date: datetime,
    athlete_timezone: str | None,
    fallback: str,
) -> str:
    """Name the timezone for a GPS-less FIT session that reports a UTC offset.

    Prefers the athlete's own zone **when it agrees with the offset the device
    recorded**. An offset is not a timezone: turning it into a fixed-offset
    ``Etc/GMT±H`` name is DST-free by construction, so the same athlete's indoor
    rides would be stamped ``Etc/GMT+8`` in January and ``Etc/GMT+7`` in July.
    Their profile zone (``America/Los_Angeles``) is the stable, DST-correct
    answer for both — and it is the *same* instant either way, so preferring it
    loses nothing.

    When the offsets disagree the athlete was somewhere other than home, and the
    device's offset is the better evidence of where they actually were; that
    falls through to a fixed-offset zone.

    Args:
        offset_seconds: UTC offset reported by the FIT file, in seconds.
        reference_date: Instant the offset was observed at, used to evaluate
            candidate zones DST-aware.
        athlete_timezone: The owner's configured IANA timezone, if any.
        fallback: Zone to keep when the offset names no zone at all.

    Returns:
        An IANA timezone name.
    """
    if athlete_timezone:
        try:
            athlete_offset = reference_date.astimezone(ZoneInfo(athlete_timezone)).utcoffset()
        except (ValueError, KeyError):
            athlete_offset = None
        if athlete_offset is not None and athlete_offset.total_seconds() == offset_seconds:
            return athlete_timezone

    # ``find_timezone_name`` can legitimately fail to name a zone for an unusual
    # offset; keep the caller's fallback rather than storing None (which
    # downstream formatting cannot use).
    return find_timezone_name(offset_seconds, reference_date) or fallback


def find_timezone_name(offset_seconds: int, reference_date: datetime) -> str | None:
    """Name a timezone for a FIT file that reports only a UTC offset.

    A bare offset does not identify a zone — dozens share any given offset, and
    they disagree about DST. Iterating ``available_timezones()`` and returning the
    first match was effectively a lottery (``+00:00`` could yield
    ``Africa/Abidjan``), and the winning name then carried the wrong DST rules for
    every other date of the year.

    So prefer the fixed-offset ``Etc/GMT±H`` zones, which encode exactly what the
    device actually told us — this offset, no DST — and are stable across runs.
    Note the POSIX sign inversion: ``Etc/GMT-9`` is UTC**+**9. Offsets that are not
    a whole number of hours (India +05:30, Nepal +05:45, Chatham +12:45) have no
    ``Etc/`` equivalent, so fall back to scanning, sorted for determinism.

    Args:
        offset_seconds: UTC offset reported by the FIT file, in seconds.
        reference_date: Instant the offset was observed at, used to evaluate
            candidate zones DST-aware.

    Returns:
        An IANA timezone name, or ``None`` when no zone matches the offset.
    """
    if offset_seconds % 3600 == 0:
        hours = int(offset_seconds // 3600)
        if -12 <= hours <= 14:
            # POSIX-style inverted sign: Etc/GMT-9 == UTC+9.
            candidate = f"Etc/GMT{-hours:+d}" if hours != 0 else "UTC"
            if candidate == "UTC" or candidate in available_timezones():
                return candidate

    for tz_name in sorted(available_timezones()):
        tz = ZoneInfo(tz_name)

        # Get the UTC offset of the candidate timezone for
        # the reference date (DST-aware).
        utc_offset = reference_date.astimezone(tz).utcoffset()
        if utc_offset is None:  # Skip invalid timezones
            continue

        if utc_offset.total_seconds() == offset_seconds:
            return tz_name

    logger.warning(
        "FIT: no timezone matches the UTC offset; falling back to the server timezone",
        extra=core_logger.context(offset_seconds=offset_seconds),
    )
    return None
