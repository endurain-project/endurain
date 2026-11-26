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

import bisect
import statistics
from collections.abc import Collection, Mapping, Sequence
from datetime import UTC, datetime
from itertools import pairwise
from statistics import mean
from typing import Any

import numpy as np
from geopy.distance import geodesic, great_circle

import modules.activities.activity_streams.contracts as activity_streams_contracts

_NP_WINDOW_SECONDS = 30

#: The slowest speed in m/s at which a step between two samples counts as moving.
MOVING_SPEED_MINIMUM = 0.5

#: The slowest speed in m/s that is still moving on water, where swimmers and paddlers go slower than on land.
MOVING_SPEED_MINIMUM_ON_WATER = 0.3

#: The span in seconds of the window whose straight-line distance decides whether a recording is moving.
MOVING_WINDOW_SECONDS = 10.0

#: The length in seconds of the window whose mean speed is the maximum speed.
MAX_SPEED_WINDOW_SECONDS = 5.0


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


def calculate_step_speed(
    prev_time: datetime | None,
    waypoint_time: datetime,
    latitude: float,
    longitude: float,
    prev_latitude: float | None,
    prev_longitude: float | None,
) -> float:
    """Compute the m/s speed between two positions over the real time step between them.

    Args:
        prev_time: Previous position timestamp; ``None`` returns 0.
        waypoint_time: Current position timestamp.
        latitude: Current latitude (decimal degrees).
        longitude: Current longitude (decimal degrees).
        prev_latitude: Previous latitude (decimal degrees).
        prev_longitude: Previous longitude (decimal degrees).

    Returns:
        The distance over the elapsed seconds, sub-second steps included; 0 when the clock does not advance or a
        previous position is missing.
    """
    if prev_time is None or prev_latitude is None or prev_longitude is None:
        return 0
    seconds = (waypoint_time - prev_time).total_seconds()
    if seconds <= 0:
        return 0
    distance = geodesic((prev_latitude, prev_longitude), (latitude, longitude)).meters
    return distance / seconds


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


def displacement_speeds(
    times: Sequence[float],
    lats: Sequence[float | None],
    lons: Sequence[float | None],
    run_starts: Collection[int],
) -> list[float | None]:
    """Return each sample's speed over a centred ``MOVING_WINDOW_SECONDS`` window of its run.

    The speed is the straight-line distance between the first and the last positioned sample of the window over the
    time between them. GPS jitter around a place where the athlete stands makes every step look fast but covers no
    distance over the window, so this, not the step speed, tells standing from moving. The window never crosses into
    another run, so a pause does not stretch it.

    Args:
        times: Sample times in seconds, in recording order.
        lats: Latitude of each sample, ``None`` where it has no position.
        lons: Longitude of each sample, ``None`` where it has no position.
        run_starts: The sample indexes that start a new run of recording, after a pause or a gap.

    Returns:
        The speed in m/s of each sample; ``None`` for a sample without a position or whose window covers no time.
    """
    speeds: list[float | None] = [None] * len(times)
    bounds = [0, *sorted(start for start in run_starts if 0 < start < len(times)), len(times)]
    for first, last in pairwise(bounds):
        rows = [row for row in range(first, last) if lats[row] is not None and lons[row] is not None]
        run_times = [times[row] for row in rows]
        half = MOVING_WINDOW_SECONDS / 2
        for row, time in zip(rows, run_times, strict=True):
            start = rows[bisect.bisect_left(run_times, time - half)]
            end = rows[bisect.bisect_right(run_times, time + half) - 1]
            span = times[end] - times[start]
            if span > 0:
                metres = great_circle((lats[start], lons[start]), (lats[end], lons[end])).meters
                speeds[row] = metres / span
    return speeds


def moving_distance(
    times: Sequence[float],
    lats: Sequence[float | None],
    lons: Sequence[float | None],
    speeds: Sequence[float | None],
    max_gap: float,
    run_starts: Collection[int],
    *,
    min_speed: float = MOVING_SPEED_MINIMUM,
) -> float:
    """Return the geodesic distance in metres of the steps :func:`moving_time` counts as moving.

    A step runs between consecutive positioned samples of one run of recording; it counts when it is at most
    ``max_gap`` long and the speed of the sample that ends it is at least ``min_speed`` (or unknown), so the GPS
    jitter of an athlete standing still adds no distance, as it adds no moving time.

    Args:
        times: Sample times in seconds, in recording order.
        lats: Latitude of each sample, ``None`` where it has no position.
        lons: Longitude of each sample, ``None`` where it has no position.
        speeds: The speed in m/s that decides whether the step ending at each sample is moving, ``None`` if unknown.
        max_gap: The longest step in seconds that is still moving, the pause threshold.
        run_starts: The sample indexes that start a new run of recording, after a pause or a gap.
        min_speed: The slowest speed in m/s that is moving.

    Returns:
        The distance in metres; 0 with fewer than two positioned samples.
    """
    total = 0.0
    previous: int | None = None
    for row, (lat, lon) in enumerate(zip(lats, lons, strict=True)):
        if row in run_starts:
            previous = None
        if lat is None or lon is None:
            continue
        if previous is not None:
            step = times[row] - times[previous]
            speed = speeds[row]
            if 0 < step <= max_gap and (speed is None or speed >= min_speed):
                total += geodesic((lats[previous], lons[previous]), (lat, lon)).meters
        previous = row
    return total


def moving_time(
    times: Sequence[float],
    speeds: Sequence[float | None],
    max_gap: float,
    *,
    min_speed: float = MOVING_SPEED_MINIMUM,
) -> float:
    """Return the seconds spent moving: the steps at ``min_speed`` or more within ``max_gap``.

    A step runs from the latest earlier time to the next later one; its speed is that of the sample that ends it. A
    step counts when its time is at most ``max_gap`` (a longer one is a pause) and its speed is at least
    ``min_speed``. A step whose sample has no speed counts by the gap rule alone, so a series with no
    speeds at all gives the gap-only moving time. Duplicate and out-of-order times add nothing and do not become the
    baseline.

    Args:
        times: Sample times in seconds, in recording order; sub-second values are allowed.
        speeds: The speed in m/s at each time, ``None`` where there is none.
        max_gap: The longest step in seconds that is still moving, the pause threshold.
        min_speed: The slowest speed in m/s that is moving.

    Returns:
        The moving time in seconds; 0 with fewer than two samples.
    """
    total = 0.0
    baseline = None
    for time, speed in zip(times, speeds, strict=True):
        if baseline is None:
            baseline = time
            continue
        step = time - baseline
        if step <= 0:
            continue
        if step <= max_gap and (speed is None or speed >= min_speed):
            total += step
        baseline = time
    return total


def rolling_max_speed(times: Sequence[float], speeds: Sequence[float | None], max_gap: float) -> float | None:
    """Return the highest mean speed over a ``MAX_SPEED_WINDOW_SECONDS`` window of time.

    Each measured speed holds over the step that ends at its sample, from the previous instant. Samples sharing an
    instant share it as their mean. A placeholder (``None``) is not a measurement but still marks where the next step
    starts, and a step longer than ``max_gap`` is a pause and is left out. The window ends at each step's end and is
    the time-weighted mean of the steps it covers, so a single spike is averaged with the seconds around it whatever
    the sampling rate. Only windows covered in full count, so a window never spans a pause; with no full window (under
    5 s of contiguous speed) the plain maximum of the measured speeds is returned.

    Args:
        times: Sample times in seconds, in recording order; sub-second values are allowed.
        speeds: The speed in m/s at each time, ``None`` for a placeholder.
        max_gap: The longest step in seconds that is a measurement, the pause threshold.

    Returns:
        The maximum speed in m/s; ``None`` when there is no measured speed.
    """
    measured = [speed for speed in speeds if speed is not None]
    if not measured:
        return None
    instants, group = np.unique(np.array(times, dtype=float), return_inverse=True)
    present = np.array([speed is not None for speed in speeds], dtype=float)
    sums = np.bincount(group, weights=np.array([0.0 if speed is None else speed for speed in speeds], dtype=float))
    counts = np.bincount(group, weights=present)
    gaps = np.diff(instants)
    kept = (counts[1:] > 0) & (gaps <= max_gap)
    if not kept.any():
        return max(measured)
    starts, ends = instants[:-1][kept], instants[1:][kept]
    steps = (sums[1:] / np.maximum(counts[1:], 1.0))[kept]
    edges = np.column_stack((starts, ends)).ravel()
    lengths = ends - starts
    length_total = np.concatenate(([0.0], np.cumsum(lengths)))[1:]
    value_total = np.cumsum(lengths * steps)
    covered = np.column_stack((length_total - lengths, length_total)).ravel()
    integral = np.column_stack((value_total - lengths * steps, value_total)).ravel()
    window_starts = ends - MAX_SPEED_WINDOW_SECONDS
    held = np.interp(ends, edges, covered) - np.interp(window_starts, edges, covered, left=0.0)
    area = np.interp(ends, edges, integral) - np.interp(window_starts, edges, integral, left=0.0)
    full = held >= MAX_SPEED_WINDOW_SECONDS - 1e-3
    if not full.any():
        return max(measured)
    return float(np.max(area[full] / held[full]))


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
