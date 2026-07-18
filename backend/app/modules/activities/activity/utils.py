"""Activity search, file relocation and metric-computation helpers.

File parsing, ingestion orchestration, and reverse-geocoding now live in the
ingestion / parsing layer (:mod:`modules.activities.activity_ingestion` and
:mod:`modules.activities.activity_file_import`); this module keeps only the
side-effect-free helpers still shared by the activities core and the file parsers
(search escaping, safe file relocation, activity-type mapping, and the
pace/elevation/speed/summary math). It performs no network or database I/O.
"""

import statistics
from datetime import datetime
from statistics import mean

from geopy.distance import geodesic

import core.file_uploads as core_file_uploads
from modules.activities.activity.constants import (
    ACTIVITY_ID_TO_NAME,
    ACTIVITY_NAME_TO_ID,
)


def escape_like(term: str) -> str:
    """Escape SQL LIKE wildcards in a user-provided term.

    Escapes ``\\``, ``%`` and ``_`` so they are matched
    literally. Use together with ``.like(..., escape="\\\\")``.

    Args:
        term: Raw search term.

    Returns:
        Escaped search term safe for use inside a ``LIKE``
        pattern.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def move_file(new_dir: str, new_filename: str, file_path: str) -> None:
    """Move ``file_path`` into ``new_dir`` as ``new_filename``.

    Thin compatibility wrapper around
    :func:`core.file_uploads.move_within`. New code should call
    ``move_within`` directly so callers benefit from path
    containment without an intermediate hop.

    Args:
        new_dir: Destination directory (created if missing).
        new_filename: Final filename inside ``new_dir``.
        file_path: Source path to move.

    Raises:
        HTTPException: 400 for unsafe filename / containment
            violations, 500 for I/O failures.
    """
    core_file_uploads.move_within(file_path, new_dir, filename=new_filename)


def append_if_not_none(
    waypoint_list: list[dict],
    waypoint_time,
    value,
    key: str,
) -> None:
    """Append ``{time, key: value}`` to ``waypoint_list`` if value is set.

    Args:
        waypoint_list: List to mutate in place.
        waypoint_time: Timestamp associated with the value.
        value: The value to record; ignored when ``None``.
        key: Dict key under which ``value`` is stored.
    """
    if value is not None:
        waypoint_list.append({"time": waypoint_time, key: value})


def calculate_instant_speed(
    prev_time,
    waypoint_time,
    latitude: float,
    longitude: float,
    prev_latitude: float | None,
    prev_longitude: float | None,
) -> float:
    """Compute m/s speed between two GPS waypoints.

    Args:
        prev_time: Previous waypoint timestamp; ``None`` returns 0.
        waypoint_time: Current waypoint timestamp.
        latitude: Current latitude (decimal degrees).
        longitude: Current longitude (decimal degrees).
        prev_latitude: Previous latitude (decimal degrees).
        prev_longitude: Previous longitude (decimal degrees).

    Returns:
        Instantaneous speed in m/s, or 0 when the time delta is
        non-positive or ``prev_time`` is missing.
    """
    if prev_time is None or prev_latitude is None or prev_longitude is None:
        return 0

    time_difference = (waypoint_time - prev_time).total_seconds()

    if time_difference <= 0:
        return 0

    distance = geodesic(
        (prev_latitude, prev_longitude),
        (latitude, longitude),
    ).meters
    return distance / time_difference


def compute_elevation_gain_and_loss(
    elevations: list[dict],
    median_window: int = 6,
    avg_window: int = 3,
    threshold: float = 0.1,
) -> tuple[float, float]:
    """Compute total elevation gain/loss in meters from waypoints.

    Applies a median filter then a moving-average smoother before
    summing per-step deltas above ``threshold``.

    Args:
        elevations: List of dicts with an ``ele`` key (meters).
        median_window: Window size for the median pre-filter.
        avg_window: Window size for the moving-average smoother.
        threshold: Minimum |delta| (m) counted toward gain/loss.

    Returns:
        Tuple of (gain_m, loss_m).
    """

    # 1) Median Filter
    def median_filter(values, window_size):
        if window_size < 2:
            return values[:]
        half = window_size // 2
        filtered = []
        for i in range(len(values)):
            start = max(0, i - half)
            end = min(len(values), i + half + 1)
            window_vals = values[start:end]
            m = statistics.median(window_vals)
            filtered.append(m)
        return filtered

    # 2) Moving-Average Smoothing
    def moving_average(values, window_size):
        if window_size < 2:
            return values[:]
        half = window_size // 2
        smoothed = []
        n = len(values)
        for i in range(n):
            start = max(0, i - half)
            end = min(n, i + half + 1)
            window_vals = values[start:end]
            smoothed.append(statistics.mean(window_vals))
        return smoothed

    try:
        # Get the values from the elevations
        values = [float(waypoint["ele"]) for waypoint in elevations]
    except (ValueError, KeyError):
        # If there are no valid values, return 0
        return 0, 0

    # Apply median filter -> then average smoothing
    filtered = median_filter(values, median_window)
    filtered = moving_average(filtered, avg_window)

    # 3) Compute gain/loss with threshold
    total_gain = 0.0
    total_loss = 0.0
    for i in range(1, len(filtered)):
        diff = filtered[i] - filtered[i - 1]
        if diff > threshold:
            total_gain += diff
        elif diff < -threshold:
            total_loss -= diff  # diff is negative, so subtracting it is adding positive
    return total_gain, total_loss


def calculate_pace(
    distance: float,
    first_waypoint_time,
    last_waypoint_time,
) -> float:
    """Compute average pace (seconds per meter).

    Args:
        distance: Total distance in meters.
        first_waypoint_time: Datetime of the first waypoint.
        last_waypoint_time: Datetime of the last waypoint.

    Returns:
        Pace in s/m, or 0 when ``distance`` is 0.
    """
    # If the distance is 0, return 0
    if distance == 0:
        return 0

    # Convert the time strings to datetime objects
    start_datetime = datetime.fromisoformat(first_waypoint_time.strftime("%Y-%m-%dT%H:%M:%S"))
    end_datetime = datetime.fromisoformat(last_waypoint_time.strftime("%Y-%m-%dT%H:%M:%S"))

    # Calculate the time difference in seconds
    total_time_in_seconds = (end_datetime - start_datetime).total_seconds()

    # Calculate pace in seconds per meter
    pace_seconds_per_meter = total_time_in_seconds / distance

    # Return the pace
    return pace_seconds_per_meter


def calculate_avg_and_max(data: list[dict], stream_type: str, exclude_zeros: bool = False) -> tuple[float, float]:
    """Compute the mean and max of ``stream_type`` across waypoints.

    Zero values are always excluded when ``stream_type`` is ``"hr"`` because
    zero is not a physiologically valid heart rate — it is a sentinel emitted
    by sensors when they lose signal. Callers may also set ``exclude_zeros``
    explicitly for other stream types.

    Args:
        data: List of waypoint dicts.
        stream_type: Key to read from each waypoint.
        exclude_zeros: When ``True``, values equal to zero are excluded.
            Automatically ``True`` when ``stream_type`` is ``"hr"``.

    Returns:
        Tuple of (avg, max), or (0, 0) when no values are present.
    """
    try:
        # Get the values from the data
        values = [float(waypoint[stream_type]) for waypoint in data if waypoint.get(stream_type) is not None]
    except (ValueError, KeyError, TypeError):
        # If there are no valid values, return 0
        return 0, 0

    if exclude_zeros or stream_type == "hr":
        values = [v for v in values if v != 0]

    if not values:
        return 0, 0

    # Calculate the average and max values
    avg_value = mean(values)
    max_value = max(values)

    return avg_value, max_value


def calculate_np(data: list[dict]) -> float:
    """Compute Normalized Power (NP) from power waypoints.

    Args:
        data: List of waypoint dicts with a ``power`` key.

    Returns:
        Normalized Power in watts, or 0 when no values are present.
    """
    try:
        # Get the power values from the data
        values = [float(waypoint["power"]) for waypoint in data if waypoint["power"] is not None]
    except (ValueError, KeyError, TypeError):
        # If there are no valid values, return 0
        return 0

    if not values:
        return 0

    # Calculate the fourth power of each power value
    fourth_powers = [p**4 for p in values]

    # Calculate the average of the fourth powers
    avg_fourth_power = sum(fourth_powers) / len(fourth_powers)

    # Take the fourth root of the average of the fourth powers to get Normalized Power
    normalized_power = avg_fourth_power ** (1 / 4)

    return normalized_power


def define_activity_type(activity_type_name: str) -> int:
    """
    Maps an activity type name (string) to its corresponding ID (integer).
    Uses the global ACTIVITY_NAME_TO_ID dictionary.
    Returns 10 (Workout) if the name is not found.
    """
    # Default value
    default_type_id = 10

    # Get the activity type ID from the global mapping (case-insensitive)
    # Ensure input is a string before lowercasing
    if isinstance(activity_type_name, str):
        return ACTIVITY_NAME_TO_ID.get(activity_type_name.lower(), default_type_id)
    else:
        # Handle non-string input if necessary, or return default
        return default_type_id


def set_activity_name_based_on_activity_type(activity_type_id: int) -> str:
    """
    Maps an activity type ID (integer) to its corresponding name (string).
    Uses the global ACTIVITY_ID_TO_NAME dictionary.
    Returns "Workout" if the ID is not found or is 10.
    Appends " workout" suffix if the name is not "Workout".
    """
    # Get the mapping for the activity type ID, default to "Workout"
    mapping = ACTIVITY_ID_TO_NAME.get(activity_type_id, "Workout")

    # If type is not 10 (Workout), return the mapping with " workout" suffix
    return mapping + " workout" if mapping != "Workout" else mapping
