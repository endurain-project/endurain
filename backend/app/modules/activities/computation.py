"""Pure activity metric computations, published by the activities module.

Turn raw waypoint streams into activity metrics (speed, elevation, pace,
averages, normalized power). Side-effect-free: no network, database or
filesystem I/O, and no import of any other module.

Module-level rather than inside a sub-package because two different consumers
need them — the file parsers and the Strava adapter — and the Strava one is
outside this module. Living in ``activity_file_import`` made
that a reach into a package whose whole contract is "parsers only"; living here
says the activities namespace publishes its metric maths alongside its explicit
composition and contributor surfaces.
"""

import statistics
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from itertools import pairwise
from statistics import mean
from typing import Any

import numpy as np
from geopy.distance import geodesic

import modules.activities.activity_streams.contracts as activity_streams_contracts

_NP_WINDOW_SECONDS = 30


def _elapsed_seconds(start: datetime, end: datetime) -> float:
    """Return real elapsed seconds between two timestamps.

    Both bounds are converted to UTC first. Subtracting them as-is is not enough:
    when two aware datetimes share a ``tzinfo`` **object**, Python documents that
    the offsets are ignored and the result is a plain wall-clock difference — so
    an activity spanning a DST transition reported an hour more (or less) than it
    actually took. Naive inputs are assumed UTC, which is the convention every
    parser writes timestamps in.

    Args:
        start: Start timestamp.
        end: End timestamp.

    Returns:
        Elapsed seconds.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    return (end.astimezone(UTC) - start.astimezone(UTC)).total_seconds()


def calculate_instant_speed(
    prev_time: datetime | None,
    waypoint_time: datetime,
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
        non-positive or ``prev_time`` is missing. Deltas shorter than one
        second count as one second so near-simultaneous fixes cannot inflate
        the speed.
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
    return distance / max(time_difference, 1)


ELEVATION_MEDIAN_WINDOW = 9
ELEVATION_AVG_WINDOW = 21
ELEVATION_THRESHOLD = 0.1
ELEVATION_SMOOTHING_SECONDS = 10.0

#: The fewest sample gaps the elevation smoothing window spans: ten, as 10 s does at 1 Hz.
ELEVATION_SMOOTHING_SAMPLES = 10
ELEVATION_HYSTERESIS = 3.0


def _median_filter(values: list[float], window_size: int) -> list[float]:
    """Smooth a series with a centred sliding median.

    Args:
        values: Samples to smooth.
        window_size: Window width; below 2 returns a copy.

    Returns:
        The filtered series, the same length as the input.
    """
    if window_size < 2:
        return values[:]
    half = window_size // 2
    n = len(values)
    return [statistics.median(values[max(0, i - half) : min(n, i + half + 1)]) for i in range(n)]


def _moving_average(values: list[float], window_size: int) -> list[float]:
    """Smooth a series with a centred sliding mean.

    Args:
        values: Samples to smooth.
        window_size: Window width; below 2 returns a copy.

    Returns:
        The smoothed series, the same length as the input.
    """
    if window_size < 2:
        return values[:]
    half = window_size // 2
    n = len(values)
    return [statistics.mean(values[max(0, i - half) : min(n, i + half + 1)]) for i in range(n)]


def _smooth_elevations(
    values: list[float],
    median_window: int,
    avg_window: int,
) -> list[float]:
    """Apply the median filter followed by the moving average.

    Args:
        values: Elevation samples in meters.
        median_window: Window size for the median pre-filter.
        avg_window: Window size for the moving-average smoother.

    Returns:
        The smoothed series, the same length as the input.
    """
    return _moving_average(_median_filter(values, median_window), avg_window)


def smooth_elevation_stream(
    elevations: Sequence[Mapping[str, Any]],
    median_window: int = ELEVATION_MEDIAN_WINDOW,
    avg_window: int = ELEVATION_AVG_WINDOW,
) -> Sequence[Mapping[str, Any]]:
    """Return an elevation stream with ``ele`` smoothed and other keys unchanged.

    Uses the same series that :func:`compute_elevation_gain_and_loss` sums, so the
    stored stream and the gain/loss agree. The whole stream is filtered at once.

    Args:
        elevations: List of dicts with ``time`` and ``ele`` keys (meters).
        median_window: Window size for the median pre-filter.
        avg_window: Window size for the moving-average smoother.

    Returns:
        New list of dicts with smoothed ``ele``; the input unchanged if any
        ``ele`` value is missing or not numeric.
    """
    try:
        values = [float(waypoint["ele"]) for waypoint in elevations]
    except ValueError, KeyError, TypeError:
        return elevations
    smoothed = _smooth_elevations(values, median_window, avg_window)
    return [{**waypoint, "ele": ele} for waypoint, ele in zip(elevations, smoothed, strict=True)]


def sum_elevation_deltas(
    elevations: Sequence[Mapping[str, Any]],
    threshold: float = ELEVATION_THRESHOLD,
) -> tuple[float, float]:
    """Sum per-step elevation deltas above ``threshold``.

    Expects an already-smoothed series and applies no smoothing itself. Laps
    slice the stream smoothed once by :func:`smooth_elevation_stream`:
    re-smoothing each slice clips gain at every lap boundary through filter
    edge effects, so per-lap sums would no longer partition the activity total.

    Args:
        elevations: List of dicts with an ``ele`` key (meters).
        threshold: Minimum |delta| (m) counted toward gain/loss.

    Returns:
        Tuple of (gain_m, loss_m); (0.0, 0.0) for empty input.
    """
    total_gain = 0.0
    total_loss = 0.0
    for previous, current in pairwise(elevations):
        diff = current["ele"] - previous["ele"]
        if diff > threshold:
            total_gain += diff
        elif diff < -threshold:
            total_loss -= diff
    return total_gain, total_loss


def compute_elevation_gain_and_loss(
    elevations: Sequence[Mapping[str, Any]],
    median_window: int = ELEVATION_MEDIAN_WINDOW,
    avg_window: int = ELEVATION_AVG_WINDOW,
    threshold: float = ELEVATION_THRESHOLD,
) -> tuple[float, float] | tuple[None, None]:
    """Compute total elevation gain/loss in meters from waypoints.

    Applies a median filter then a moving-average smoother before
    summing per-step deltas above ``threshold``.

    Args:
        elevations: List of dicts with an ``ele`` key (meters).
        median_window: Window size for the median pre-filter.
        avg_window: Window size for the moving-average smoother.
        threshold: Minimum |delta| (m) counted toward gain/loss.

    Returns:
        Tuple of (gain_m, loss_m); (0.0, 0.0) for a flat stream, and
        (None, None) when the stream is empty or holds no valid values.
    """
    try:
        values = [float(waypoint["ele"]) for waypoint in elevations]
    except ValueError, KeyError, TypeError:
        return None, None
    if not values:
        return None, None

    filtered = _smooth_elevations(values, median_window, avg_window)
    return sum_elevation_deltas([{"ele": ele} for ele in filtered], threshold)


def smooth_elevation(times: Sequence[float], values: Sequence[float]) -> list[float]:
    """Smooth an elevation series with a centred time-window mean.

    Each sample becomes the mean of every sample within half the window either side of it, ends included. The window
    is ``ELEVATION_SMOOTHING_SECONDS``, widened to ``ELEVATION_SMOOTHING_SAMPLES`` times the median gap between samples
    when the recording is sparser, so a 5 s or 10 s recording averages as many samples as a 1 Hz one and its noise is
    smoothed alike instead of passing the hysteresis as climbs. The samples may come in any order; the result is in
    the order given. Every value must be a number.

    Args:
        times: Sample times in seconds.
        values: The altitude in metres at each time.

    Returns:
        The smoothed altitudes, one per sample; empty for no samples.
    """
    if not len(times):
        return []
    order = np.argsort(np.asarray(times, dtype=float), kind="stable")
    instants = np.asarray(times, dtype=float)[order]
    cumulative = np.concatenate(([0.0], np.cumsum(np.asarray(values, dtype=float)[order])))
    gaps = np.diff(instants)
    sampling = float(np.median(gaps)) if len(gaps) else 0.0
    half = max(ELEVATION_SMOOTHING_SECONDS, ELEVATION_SMOOTHING_SAMPLES * sampling) / 2
    first = np.searchsorted(instants, instants - half, side="left")
    last = np.searchsorted(instants, instants + half, side="right")
    smoothed = np.empty(len(instants))
    smoothed[order] = (cumulative[last] - cumulative[first]) / (last - first)
    return smoothed.tolist()


def elevation_steps(values: Sequence[float]) -> tuple[list[float], list[float]]:
    """Count the climbing and descending of a smoothed elevation series with a hysteresis.

    A reference level starts at the first value. A value at least ``ELEVATION_HYSTERESIS`` metres above it counts the
    rise as gain, and one at least that far below counts the drop as loss; either moves the reference to that value.
    The gain and loss are returned at the sample that confirms them, so the total of any run of samples is the sum
    of its entries and runs that follow one another add up to the whole series.

    Args:
        values: The smoothed altitudes in metres, in recording order.

    Returns:
        The gain and the loss counted at each sample, in metres; both empty for no samples.
    """
    gains = [0.0] * len(values)
    losses = [0.0] * len(values)
    reference = values[0] if len(values) else 0.0
    for i, value in enumerate(values):
        change = value - reference
        if change >= ELEVATION_HYSTERESIS:
            gains[i] = change
            reference = value
        elif change <= -ELEVATION_HYSTERESIS:
            losses[i] = -change
            reference = value
    return gains, losses


def calculate_pace(
    distance: float,
    first_waypoint_time: datetime,
    last_waypoint_time: datetime,
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

    total_time_in_seconds = _elapsed_seconds(first_waypoint_time, last_waypoint_time)

    # Calculate pace in seconds per meter
    pace_seconds_per_meter = total_time_in_seconds / distance

    # Return the pace
    return pace_seconds_per_meter


def calculate_pace_from_duration(
    distance: float,
    duration_seconds: float,
) -> float:
    """Compute average pace (seconds per meter) from an active duration.

    Mirrors the FIT importer semantics (pace = timer time / distance) so
    GPX/TCX imports exclude recording pauses from pace (issue #571).

    Args:
        distance: Total distance in meters.
        duration_seconds: Active (timer) time in seconds.

    Returns:
        Pace in s/m, or 0 when ``distance`` is 0 or the duration is not
        positive.
    """
    if distance == 0 or duration_seconds <= 0:
        return 0

    return duration_seconds / distance


def calculate_avg_and_max(
    data: Sequence[Mapping[str, Any]],
    stream_type: str,
    exclude_zeros: bool = False,
) -> tuple[float, float]:
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
    except ValueError, KeyError, TypeError:
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


def time_weighted_mean(times: Sequence[float], values: Sequence[float | None], max_gap: float) -> float | None:
    """Return the mean of ``values`` with each sample weighted by the time it holds until the next one.

    A sample that is ``None`` is left out together with its time: the weight of the previous kept sample runs to the
    next kept one. Each weight is capped at ``max_gap``, so a pause weighs nothing beyond it. The last instant weighs
    nothing unless it is the only one, which then is the mean. Samples sharing an instant share its time equally, so a
    stream stamped to the whole second keeps every sample of a second.

    Args:
        times: Sample times in seconds, in recording order; sub-second values are allowed.
        values: The value at each time, ``None`` where the channel has none.
        max_gap: The longest weight in seconds a sample can hold, the pause threshold.

    Returns:
        The time-weighted mean; ``None`` when no sample has a value.
    """
    kept = [(time, value) for time, value in zip(times, values, strict=True) if value is not None]
    if not kept:
        return None
    instants, group = np.unique(np.array([time for time, _ in kept], dtype=float), return_inverse=True)
    sums = np.bincount(group, weights=np.array([value for _, value in kept], dtype=float))
    means = sums / np.bincount(group)
    if len(instants) == 1:
        return float(means[0])
    weights = np.clip(np.diff(instants), 0.0, max_gap)
    total = weights.sum()
    if total == 0.0:
        return float(means.mean())
    return float(np.dot(weights, means[:-1]) / total)


def normalized_power(times: Sequence[float], values: Sequence[float | None], max_gap: float) -> float | None:
    """Return the normalized power (Coggan) of a power series.

    The series is resampled to 1 Hz over the time it was recorded: each sample holds its value until the next one,
    and each second is the average power over that second, so a power meter faster than 1 Hz keeps every reading and
    a smart-recording file its held values. A sample followed by a gap longer than ``max_gap``, and the last sample,
    hold only their own second, so a pause adds no seconds and is not zero-filled. Samples sharing one instant are
    averaged. A sample is left out together with its time when its power is ``None``; a power of 0 counts. The result
    is the 4th root of the mean 4th power of the 30 s rolling mean.

    Args:
        times: Sample times in seconds, in recording order; sub-second values are allowed.
        values: The power at each time, ``None`` where the channel has none.
        max_gap: The longest gap in seconds that a sample still holds its value through, the pause threshold.

    Returns:
        The normalized power in watts; ``None`` when fewer than 30 seconds of power remain.
    """
    kept = [(time, value) for time, value in zip(times, values, strict=True) if value is not None]
    if not kept:
        return None
    instants, group = np.unique(np.array([time for time, _ in kept], dtype=float), return_inverse=True)
    means = np.bincount(group, weights=np.array([value for _, value in kept], dtype=float)) / np.bincount(group)
    steps = np.diff(instants)
    held = np.append(np.where(steps <= max_gap, steps, 1.0), 1.0)
    elapsed = np.concatenate(([0.0], np.cumsum(held)))
    energy = np.concatenate(([0.0], np.cumsum(means * held)))
    whole_seconds = int(np.floor(elapsed[-1]))
    if whole_seconds < _NP_WINDOW_SECONDS:
        return None
    seconds = np.diff(np.interp(np.arange(whole_seconds + 1, dtype=float), elapsed, energy))
    rolling = np.convolve(seconds, np.ones(_NP_WINDOW_SECONDS) / _NP_WINDOW_SECONDS, mode="valid")
    return float(np.mean(rolling**4) ** 0.25)


def calculate_robust_max(values: list[float], window: int = 5) -> float:
    """Return the maximum of the sliding-window medians of ``values``.

    A single GPS glitch never becomes the maximum because every candidate is the
    median of ``window`` consecutive samples. Only full windows are considered;
    the algorithm mirrors the mobile app so both report the same value.

    Args:
        values: Samples in chronological order.
        window: Number of consecutive samples per median.

    Returns:
        The robust maximum, the plain maximum when fewer than ``window``
        samples exist, or 0 when ``values`` is empty.
    """
    if not values:
        return 0
    if len(values) < window:
        return max(values)
    return max(statistics.median(values[i : i + window]) for i in range(len(values) - window + 1))


def calculate_np(data: Sequence[Mapping[str, Any]]) -> float:
    """Compute Normalized Power (NP) from power waypoints.

    Args:
        data: List of waypoint dicts with a ``power`` key.

    Returns:
        Normalized Power in watts, or 0 when no values are present.
    """
    try:
        # Get the power values from the data
        values = [float(waypoint["power"]) for waypoint in data if waypoint["power"] is not None]
    except ValueError, KeyError, TypeError:
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


def double_running_cadence(cadence: float | None, fractional: float | None = 0.0) -> int | None:
    """Convert a single-leg running cadence (rpm) to steps per minute (spm).

    Importers call this for running activity types when the source format
    reports a per-leg rate (FIT, Strava, TCX, GPX).

    Args:
        cadence: Single-leg cadence, or ``None``.
        fractional: FIT ``fractional_cadence`` to fold in before doubling.

    Returns:
        ``round((cadence + fractional) * 2)``, or ``None`` when ``cadence`` is ``None``.
    """
    if cadence is None:
        return None
    return round((float(cadence) + float(fractional or 0.0)) * 2)


def double_cadence_waypoints(
    waypoints: list[activity_streams_contracts.CadenceWaypoint],
) -> list[activity_streams_contracts.CadenceWaypoint]:
    """Return cadence waypoints with every ``cad`` converted from rpm to spm.

    Waypoints whose ``cad`` is ``None`` are kept unchanged.

    Args:
        waypoints: Cadence waypoints (dicts with a ``cad`` key).

    Returns:
        New waypoint dicts with ``cad`` doubled and rounded.
    """
    return [{**wp, "cad": round(wp["cad"] * 2)} if wp.get("cad") is not None else wp for wp in waypoints]
