"""Per-message extraction for the FIT format: one frame in, plain data out.

The leaf half of the FIT parser. Each ``parse_frame_*`` reads a single FIT data
message and returns a dict or primitive; none of them touches parse state, calls
another frame parser, or knows an activity exists. ``utils_fit`` holds the other
half — the dispatch that routes each message to one of these and accumulates the
result into an activity.

Split out because the two answer different questions ("what does a lap message
contain?" against "how do these messages become an activity?") and the file had
grown to 1278 lines holding both. The dependency is one-way by construction: the
dispatch imports these, and nothing here imports back.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, available_timezones

import fitdecode

import core.logger as core_logger
import modules.activities.activity.constants as activities_constants
import modules.activities.activity_exercise_titles.schema as activity_exercise_titles_schema
import modules.activities.activity_workout_steps.schema as activity_workout_steps_schema

logger = core_logger.get_logger(__name__)


def parse_frame_session(frame):
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
        elif isinstance(sub_sport, str) and sub_sport.lower() in activities_constants.ACTIVITY_NAME_TO_ID:
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
        get_value_from_frame(frame, "workout_rpe"),
        get_value_from_frame(frame, "total_cycles"),
    )


def parse_frame_workout(frame):
    # Return the extracted name
    return get_value_from_frame(frame, "wkt_name", "Workout")


def parse_frame_record(frame):
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


def parse_frame_lap(frame):
    keys = [
        "start_time",
        "start_position_lat",
        "start_position_long",
        "end_position_lat",
        "end_position_long",
        "total_elapsed_time",
        "total_timer_time",
        "total_distance",
        "total_cycles",
        "total_calories",
        "avg_heart_rate",
        "max_heart_rate",
        "avg_cadence",
        "max_cadence",
        "avg_power",
        "max_power",
        "total_ascent",
        "total_descent",
        "intensity",
        "lap_trigger",
        "sport",
        "sub_sport",
        "normalized_power",
        "total_work",
        "avg_vertical_oscillation",
        "avg_stance_time",
        "avg_fractional_cadence",
        "max_fractional_cadence",
        "enhanced_avg_speed",
        "enhanced_max_speed",
        "enhanced_min_altitude",
        "enhanced_max_altitude",
        "avg_vertical_ratio",
        "avg_step_length",
    ]

    lap_data = tuple(get_value_from_frame(frame, key) for key in keys)
    lap_dict = dict(zip(keys, lap_data, strict=False))

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


def parse_frame_split(frame):
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


def parse_frame_split_summary(frame):
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


def parse_frame_set(frame):
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


def parse_frame_workout_step(frame):
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

    return activity_workout_steps_schema.ActivityWorkoutSteps(
        message_index=workout_set_data[0] if workout_set_data[0] else 0,
        duration_type=workout_set_data[1],
        duration_value=workout_set_data[2],
        target_type=workout_set_data[3],
        target_value=workout_set_data[4] if workout_set_data[4] else None,
        intensity=workout_set_data[5] if isinstance(workout_set_data[5], str) else None,
        notes=workout_set_data[6],
        exercise_category=workout_set_data[9],
        exercise_name=workout_set_data[10] if workout_set_data[10] else None,
        exercise_weight=workout_set_data[7],
        weight_display_unit=workout_set_data[8],
        secondary_target_value=secondary_target_value,
    )


def parse_frame_exercise_title(frame):
    keys_value = [
        "wkt_step_name",
    ]

    keys_raw = [
        "exercise_category",
        "exercise_name",
    ]

    exercise_title_data = [get_value_from_frame(frame, key) for key in keys_value]
    exercise_title_data.extend(get_raw_value_from_frame(frame, key) for key in keys_raw)

    return activity_exercise_titles_schema.ActivityExerciseTitles(
        exercise_category=exercise_title_data[1] if exercise_title_data[1] else 0,
        exercise_name=exercise_title_data[2] if exercise_title_data[2] else 0,
        wkt_step_name=str(exercise_title_data[0]),
    )


def parse_frame_device_settings(frame):
    return get_value_from_frame(frame, "time_offset")


def parse_frame_length(frame):
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


def parse_frame_file_id(frame):
    return {
        "type": get_value_from_frame(frame, "type"),
        "manufacturer": get_value_from_frame(frame, "manufacturer"),
        "product": get_value_from_frame(frame, "product"),
        "serial_number": get_value_from_frame(frame, "serial_number"),
        "time_created": get_value_from_frame(frame, "time_created"),
    }


def parse_frame_monitoring(frame, last_timestamp):
    steps = []
    heart_rate = []

    data = {}
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


def parse_frame_monitoring_hr_data(frame):
    return {
        "timestamp": get_value_from_frame(frame, "timestamp"),
        "resting_heart_rate": get_value_from_frame(frame, "resting_heart_rate"),
        "current_day_resting_heart_rate": get_value_from_frame(frame, "current_day_resting_heart_rate"),
    }


def interpret_time_offset(raw_offset):
    # Check for two's complement representation (values > 2^31)
    if raw_offset != 0 and raw_offset is not None and raw_offset > 2**31 - 1:
        return raw_offset - 2**32
    return raw_offset


def get_value_from_frame(frame, key, default=None):
    try:
        value = frame.get_value(key)
        # Explicit None check so a genuine 0 (e.g. 0 m ascent, 0 W power, a lap
        # that truly covered 0 m) survives instead of collapsing to the default.
        return value if value is not None else default
    except KeyError:
        return default


def get_raw_value_from_frame(frame, key, default=None):
    try:
        raw_value = frame.get_raw_value(key)
        return raw_value if raw_value else default
    except KeyError:
        return default


def convert_coordinates_to_degrees(latitude, longitude):
    # Convert FIT coordinates to degrees if available
    if latitude is not None and longitude is not None:
        latitude = latitude * (180 / 2**31)
        longitude = longitude * (180 / 2**31)

    return latitude, longitude


def calculate_pace(distance, total_timer_time, activity_type, split_summary, lengths):
    if distance:
        if activity_type != "lap_swimming" or (activity_type == "lap_swimming" and not split_summary and not lengths):
            return total_timer_time, total_timer_time / distance
        if activity_type == "lap_swimming" and lengths:
            # Swimming pace calculation based on lengths
            time_active = 0
            for length in lengths:
                if length["length_type"] == "active":
                    time_active += length["total_timer_time"]

            return time_active, time_active / distance
        # Swimming pace calculation based on split summary
        time_active = 0
        for split in split_summary:
            if split["split_type"] != 4:
                time_active += split["total_timer_time"]

        return time_active, time_active / distance
    return total_timer_time, 0


def _timezone_from_offset(
    offset_seconds: int,
    reference_date,
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


def find_timezone_name(offset_seconds, reference_date):
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
