"""Shared math for assembling an imported activity: lap generation, distance, pauses and power."""

import bisect
import itertools
import statistics
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, TypedDict

from geopy.distance import geodesic

import core.timezone as core_timezone
import modules.activities.activity_streams.contracts as activity_streams_contracts

# ISO 8601 datetime format used throughout the import pipeline
_DT_FMT = "%Y-%m-%dT%H:%M:%S"

KM_PER_MILE = 1.609344
DEFAULT_LAP_DISTANCE_KM = 1.0

# Minimum gap in seconds between two consecutive trackpoints that counts as a
# recording pause. GPS devices record every 1-5 s (smart recording modes
# occasionally stretch further), so 15 s tolerates dropped fixes while real
# pauses (issue #571) are typically well above it. Gaps strictly greater than
# the pause threshold are excluded from timer time and from the distance
# accumulated across the gap.
PAUSE_DETECTION_THRESHOLD_SECONDS: float = 15.0

# Sparse tracks (e.g. 30 s or 60 s battery-saving recording) sample above the
# minimum, so the pause threshold is this many times the track's median
# sampling interval when that is larger. Below the minimum gap count a median
# cannot tell sparse sampling from a pause, so the minimum threshold applies.
PAUSE_DETECTION_SAMPLING_FACTOR: float = 3.0
PAUSE_DETECTION_MIN_GAPS_FOR_MEDIAN: int = 3


class LapMetrics(TypedDict):
    """Typed dictionary for a single lap's metrics.

    Attributes:
        start_time: ISO timestamp of lap start.
        start_position_lat: Latitude of lap start.
        start_position_long: Longitude of lap start.
        end_position_lat: Latitude of lap end.
        end_position_long: Longitude of lap end.
        total_elapsed_time: Elapsed seconds.
        total_timer_time: Timer seconds.
        total_distance: Distance in metres.
        avg_heart_rate: Average HR in bpm.
        max_heart_rate: Maximum HR in bpm.
        avg_cadence: Average cadence.
        max_cadence: Maximum cadence.
        avg_power: Average power in watts.
        max_power: Maximum power in watts.
        total_ascent: Total ascent in metres.
        total_descent: Total descent in metres.
        normalized_power: Normalized power.
        enhanced_avg_pace: Average pace (s/m).
        enhanced_avg_speed: Average speed (m/s).
        enhanced_max_pace: Maximum pace (s/m).
        enhanced_max_speed: Maximum speed (m/s).
    """

    start_time: str
    start_position_lat: float | None
    start_position_long: float | None
    end_position_lat: float | None
    end_position_long: float | None
    total_elapsed_time: float
    total_timer_time: float
    total_distance: float
    avg_heart_rate: int | None
    max_heart_rate: int | None
    avg_cadence: int | None
    max_cadence: int | None
    avg_power: int | None
    max_power: int | None
    total_ascent: int | None
    total_descent: int | None
    normalized_power: int | None
    enhanced_avg_pace: float | None
    enhanced_avg_speed: float | None
    enhanced_max_pace: float | None
    enhanced_max_speed: float | None


def _parse_utc(time_str: str) -> datetime:
    """Parse a parser-emitted timestamp as a UTC-aware datetime.

    Every parser writes timestamps through ``core_timezone.format_utc``, which
    emits a UTC wall clock with no offset. Attaching UTC here makes that
    convention explicit at the point of use, so comparisons and subtractions are
    aware-to-aware instead of relying on both sides happening to be naive.

    Args:
        time_str: Timestamp string in ``%Y-%m-%dT%H:%M:%S`` form.

    Returns:
        The parsed instant, as UTC-aware.
    """
    return datetime.strptime(time_str, _DT_FMT).replace(tzinfo=UTC)


class _TimedStream:
    """A waypoint stream with its timestamps parsed once, for repeated time-window lookups.

    Attributes:
        waypoints: The stream's waypoint dicts, in their original order.
        pause_threshold: The gap in seconds above which the stream's own gaps are pauses.
    """

    def __init__(self, waypoints: Sequence[Mapping[str, Any]]) -> None:
        """Parse every timestamp of the stream once.

        Args:
            waypoints: Waypoint dicts each containing a ``'time'`` key with an ISO 8601 string.
        """
        self.waypoints = waypoints
        self._times = [_parse_utc(wp["time"]) for wp in waypoints]
        self._ordered = all(a <= b for a, b in itertools.pairwise(self._times))
        self.pause_threshold = pause_threshold_seconds(self._times)

    def indices_between(self, start_dt: datetime, end_dt: datetime) -> range | list[int]:
        """Return the indices of the waypoints whose time falls within [start_dt, end_dt].

        A time-ordered stream is searched by bisection; any other order is scanned in full so the
        result never depends on the order.

        Args:
            start_dt: Inclusive lower bound.
            end_dt: Inclusive upper bound.

        Returns:
            The matching indices in ascending order.
        """
        if self._ordered:
            return range(bisect.bisect_left(self._times, start_dt), bisect.bisect_right(self._times, end_dt))
        return [i for i, time in enumerate(self._times) if start_dt <= time <= end_dt]

    def between(self, start_time: str, end_time: str) -> list[Mapping[str, Any]]:
        """Return the waypoints whose time falls within [start_time, end_time].

        Args:
            start_time: ISO 8601 start time string (inclusive).
            end_time: ISO 8601 end time string (inclusive).

        Returns:
            Filtered list of waypoint dicts.
        """
        indices = self.indices_between(_parse_utc(start_time), _parse_utc(end_time))
        return [self.waypoints[i] for i in indices]

    def lap_elevation(self, start_time: str, end_time: str) -> Sequence[Mapping[str, Any]]:
        """Return a lap's slice of this once-smoothed elevation stream (see ``slice_lap_elevation``).

        Args:
            start_time: ISO 8601 lap start (inclusive).
            end_time: ISO 8601 lap end (inclusive).

        Returns:
            The lap's elevation samples; empty when none fall within the lap.
        """
        start_dt = _parse_utc(start_time)
        indices = self.indices_between(start_dt, _parse_utc(end_time))
        if not indices:
            return []
        first = indices[0]
        if first > 0 and self._times[first] > start_dt:
            first -= 1
        return self.waypoints[first : indices[-1] + 1]


def slice_lap_elevation(
    smoothed_ele_waypoints: Sequence[Mapping[str, Any]],
    start_time: str,
    end_time: str,
) -> Sequence[Mapping[str, Any]]:
    """Return a lap's slice of the once-smoothed elevation stream.

    The slice is ``[start_time, end_time]`` plus the sample just before it when
    the lap's first sample is later than ``start_time``. Laps whose boundary
    falls between two samples then count the step across it once, in the later
    lap, and consecutive lap sums add up to the activity total. A sample exactly
    at ``start_time`` already ends the previous lap and is not extended.

    Args:
        smoothed_ele_waypoints: Time-ordered smoothed elevation stream.
        start_time: ISO 8601 lap start (inclusive).
        end_time: ISO 8601 lap end (inclusive).

    Returns:
        The lap's elevation samples; empty when none fall within the lap.
    """
    return _TimedStream(smoothed_ele_waypoints).lap_elevation(start_time, end_time)


def measured_speed_samples(
    vel_waypoints: Sequence[Mapping[str, Any]],
    measured_vel_indices: set[int] | None,
    indices: Iterable[int] | None = None,
) -> list[Mapping[str, Any]]:
    """Select the velocity samples that are real measurements.

    Args:
        vel_waypoints: Full velocity stream.
        measured_vel_indices: Positions in ``vel_waypoints`` of the measured samples; ``None``
            treats every sample as measured.
        indices: Positions to consider; ``None`` considers the whole stream.

    Returns:
        The measured samples among the considered positions, in stream order.
    """
    candidates = range(len(vel_waypoints)) if indices is None else indices
    if measured_vel_indices is None:
        return [vel_waypoints[i] for i in candidates]
    return [vel_waypoints[i] for i in candidates if i in measured_vel_indices]


def _lap_mean(
    waypoints: Sequence[Mapping[str, Any]], key: str, threshold: float, *, skip_zeros: bool = False
) -> float | None:
    """Average a lap's samples by the time each holds until the next.

    Args:
        waypoints: The lap's waypoints in time order.
        key: The waypoint key holding the value.
        threshold: The stream's pause threshold in seconds.
        skip_zeros: Leave zero values out of the average, together with their time.

    Returns:
        The time-weighted mean; ``None`` when no waypoint has a value.
    """
    import modules.activities.computation as activities_computation

    times = [_parse_utc(waypoint["time"]).timestamp() for waypoint in waypoints]
    values = [
        None if waypoint.get(key) is None or (skip_zeros and not waypoint[key]) else float(waypoint[key])
        for waypoint in waypoints
    ]
    return activities_computation.time_weighted_mean(times, values, threshold)


def _lap_normalized_power(waypoints: Sequence[Mapping[str, Any]], threshold: float) -> float | None:
    """Return the normalized power of a lap's power waypoints.

    Args:
        waypoints: The lap's power waypoints in time order.
        threshold: The stream's pause threshold in seconds.

    Returns:
        The normalized power; ``None`` when fewer than 30 seconds of power exist.
    """
    import modules.activities.computation as activities_computation

    return activities_computation.normalized_power(
        [_parse_utc(waypoint["time"]).timestamp() for waypoint in waypoints],
        [None if waypoint.get("power") is None else float(waypoint["power"]) for waypoint in waypoints],
        threshold,
    )


def _compute_lap_metrics(
    start_time: str,
    end_time: str,
    start_point: Mapping[str, Any],
    end_point: Mapping[str, Any],
    total_distance: float,
    smoothed_ele: _TimedStream,
    power: _TimedStream,
    hr: _TimedStream,
    cad: _TimedStream,
    vel: _TimedStream,
    measured_vel_indices: set[int] | None = None,
) -> LapMetrics:
    """Compute metrics for a single activity lap.

    Args:
        start_time: ISO timestamp of lap start.
        end_time: ISO timestamp of lap end.
        start_point: Lat/lon dict of lap start.
        end_point: Lat/lon dict of lap end.
        total_distance: Lap distance in km.
        smoothed_ele: Full elevation stream, already smoothed once (see smooth_elevation_stream).
        power: Full power stream.
        hr: Full HR stream.
        cad: Full cadence stream.
        vel: Full velocity stream.
        measured_vel_indices: Positions in the velocity stream of samples that are
            real measurements; average and max speed ignore the others. ``None``
            treats every sample as measured.

    Returns:
        Dict with all computed lap metrics.
    """
    # The metric helpers live in this package's dependency-free computation module.
    import modules.activities.computation as activities_computation

    lap_ele = smoothed_ele.lap_elevation(start_time, end_time)
    lap_power = power.between(start_time, end_time)
    lap_hr = hr.between(start_time, end_time)
    lap_cad = cad.between(start_time, end_time)
    lap_vel_indices = vel.indices_between(_parse_utc(start_time), _parse_utc(end_time))

    ele_gain, ele_loss = None, None
    if lap_ele:
        ele_gain, ele_loss = activities_computation.sum_elevation_deltas(lap_ele)

    avg_hr, max_hr = None, None
    if lap_hr:
        _, max_hr = activities_computation.calculate_avg_and_max(lap_hr, "hr")
        avg_hr = _lap_mean(lap_hr, "hr", hr.pause_threshold, skip_zeros=True)

    avg_cad, max_cad = None, None
    if lap_cad:
        _, max_cad = activities_computation.calculate_avg_and_max(lap_cad, "cad")
        avg_cad = _lap_mean(lap_cad, "cad", cad.pause_threshold, skip_zeros=True)

    avg_speed, max_speed = None, None
    # Placeholder samples (a segment's first point) are not speeds, so neither average nor max sees them.
    measured_vel = measured_speed_samples(vel.waypoints, measured_vel_indices, lap_vel_indices)
    if measured_vel:
        avg_speed = _lap_mean(measured_vel, "vel", vel.pause_threshold)
        max_speed = activities_computation.calculate_robust_max([waypoint["vel"] for waypoint in measured_vel])

    avg_power, max_power, norm_power = None, None, None
    if lap_power:
        _, max_power = activities_computation.calculate_avg_and_max(lap_power, "power")
        avg_power = _lap_mean(lap_power, "power", power.pause_threshold)
        norm_power = _lap_normalized_power(lap_power, power.pause_threshold)

    elapsed = (_parse_utc(end_time) - _parse_utc(start_time)).total_seconds()

    return {
        "start_time": start_time,
        "start_position_lat": start_point["lat"],
        "start_position_long": start_point["lon"],
        "end_position_lat": end_point["lat"],
        "end_position_long": end_point["lon"],
        "total_elapsed_time": elapsed,
        "total_timer_time": elapsed,
        "total_distance": total_distance * 1000,
        "avg_heart_rate": round(avg_hr) if avg_hr else None,
        "max_heart_rate": round(max_hr) if max_hr else None,
        "avg_cadence": round(avg_cad) if avg_cad else None,
        "max_cadence": round(max_cad) if max_cad else None,
        "avg_power": round(avg_power) if avg_power else None,
        "max_power": round(max_power) if max_power else None,
        # A flat lap has a genuine 0 m ascent/descent, distinct from missing data.
        "total_ascent": round(ele_gain) if ele_gain is not None else None,
        "total_descent": round(ele_loss) if ele_loss is not None else None,
        "normalized_power": round(norm_power) if norm_power else None,
        "enhanced_avg_pace": 1 / avg_speed if avg_speed else None,
        "enhanced_avg_speed": avg_speed,
        "enhanced_max_pace": 1 / max_speed if max_speed else None,
        "enhanced_max_speed": max_speed,
    }


def generate_activity_laps(
    lat_lon_waypoints: Sequence[Mapping[str, Any]],
    ele_waypoints: Sequence[Mapping[str, Any]],
    power_waypoints: Sequence[Mapping[str, Any]],
    hr_waypoints: Sequence[Mapping[str, Any]],
    cad_waypoints: Sequence[Mapping[str, Any]],
    vel_waypoints: Sequence[Mapping[str, Any]],
    distance_per_lap_km: float = DEFAULT_LAP_DISTANCE_KM,
    measured_vel_indices: set[int] | None = None,
    smoothed_ele_waypoints: Sequence[Mapping[str, Any]] | None = None,
) -> list[LapMetrics]:
    """Split waypoints into distance-based laps and compute metrics.

    Reads the streams a parser just built.

    Args:
        lat_lon_waypoints: List of lat/lon dicts.
        ele_waypoints: List of elevation dicts.
        power_waypoints: List of power dicts.
        hr_waypoints: List of heart rate dicts.
        cad_waypoints: List of cadence dicts.
        vel_waypoints: List of velocity dicts.
        distance_per_lap_km: Km per lap (default 1 km).
        measured_vel_indices: Positions in ``vel_waypoints`` of samples that are real
            measurements, for sources that emit placeholder samples; ``None``
            treats every sample as measured.
        smoothed_ele_waypoints: ``ele_waypoints`` already smoothed once (see
            smooth_elevation_stream). Callers that build laps for several
            segments of one activity pass it to avoid re-smoothing the stream;
            when None, ``ele_waypoints`` is smoothed here.

    Returns:
        List of lap dicts with computed metrics.
    """
    # The metric helpers live in this package's dependency-free computation module.
    import modules.activities.computation as activities_computation

    laps: list[LapMetrics] = []
    current_lap_distance = 0.0
    lap_start = None

    # Smooth the elevation stream once for the whole activity so the per-lap
    # slices partition the activity-level gain/loss exactly.
    if smoothed_ele_waypoints is None:
        smoothed_ele_waypoints = activities_computation.smooth_elevation_stream(ele_waypoints)

    # Each stream's timestamps are parsed once here, not once per lap.
    streams = {
        "smoothed_ele": _TimedStream(smoothed_ele_waypoints),
        "power": _TimedStream(power_waypoints),
        "hr": _TimedStream(hr_waypoints),
        "cad": _TimedStream(cad_waypoints),
        "vel": _TimedStream(vel_waypoints),
    }

    for i in range(1, len(lat_lon_waypoints)):
        prev_point = lat_lon_waypoints[i - 1]
        current_point = lat_lon_waypoints[i]

        segment_distance = geodesic(
            (prev_point["lat"], prev_point["lon"]),
            (current_point["lat"], current_point["lon"]),
        ).kilometers

        current_lap_distance += segment_distance

        if lap_start is None:
            lap_start = prev_point

        if current_lap_distance >= distance_per_lap_km:
            laps.append(
                _compute_lap_metrics(
                    start_time=lap_start["time"],
                    end_time=current_point["time"],
                    start_point=lap_start,
                    end_point=current_point,
                    total_distance=current_lap_distance,
                    **streams,
                    measured_vel_indices=measured_vel_indices,
                )
            )
            lap_start = current_point
            current_lap_distance = 0.0

    if lap_start is not None and current_lap_distance > 0:
        laps.append(
            _compute_lap_metrics(
                start_time=lap_start["time"],
                end_time=lat_lon_waypoints[-1]["time"],
                start_point=lap_start,
                end_point=lat_lon_waypoints[-1],
                total_distance=current_lap_distance,
                **streams,
                measured_vel_indices=measured_vel_indices,
            )
        )

    return laps


def resolve_timezone_from_lat_lon(
    latitude: float,
    longitude: float,
    fallback_tz: str,
) -> str:
    """Get timezone string via TimezoneFinder with a fallback.

    Args:
        latitude: WGS-84 latitude in decimal degrees.
        longitude: WGS-84 longitude in decimal degrees.
        fallback_tz: Timezone string to return when TimezoneFinder
            returns ``None``.

    Returns:
        IANA timezone string (e.g. ``'Europe/Lisbon'``).
    """
    return core_timezone.from_lat_lon(latitude, longitude, fallback_tz)


def compute_distance_from_waypoints(lat_lon_waypoints: Sequence[activity_streams_contracts.LatLonWaypoint]) -> float:
    """Compute total distance in metres from a GPS track.

    Sums the geodesic distance between consecutive waypoints. Used as a
    fallback when a source file does not provide a summary distance (e.g. a
    FIT session frame without ``total_distance``). Mirrors the accumulation
    the GPX importer already performs point-by-point.

    Args:
        lat_lon_waypoints: Ordered list of dicts each containing ``'lat'``
            and ``'lon'`` numeric keys.

    Returns:
        Total distance in metres. ``0.0`` if fewer than two valid points.
    """
    total = 0.0
    for i in range(1, len(lat_lon_waypoints)):
        prev_point = lat_lon_waypoints[i - 1]
        current_point = lat_lon_waypoints[i]
        if (
            prev_point.get("lat") is None
            or prev_point.get("lon") is None
            or current_point.get("lat") is None
            or current_point.get("lon") is None
        ):
            continue
        total += geodesic(
            (prev_point["lat"], prev_point["lon"]),
            (current_point["lat"], current_point["lon"]),
        ).meters
    return total


def pause_threshold_seconds(times: list[datetime]) -> float:
    """Return the gap in seconds above which a trackpoint gap is a pause.

    The threshold is ``PAUSE_DETECTION_SAMPLING_FACTOR`` times the median
    positive gap between consecutive timestamps, but never below
    ``PAUSE_DETECTION_THRESHOLD_SECONDS``. The median is unaffected by the
    few long gaps that real pauses produce. With fewer than
    ``PAUSE_DETECTION_MIN_GAPS_FOR_MEDIAN`` positive gaps the minimum is
    returned.

    Args:
        times: Trackpoint timestamps in recording order, without ``None``
            entries.

    Returns:
        The pause threshold in seconds.
    """
    gaps = [(b - a).total_seconds() for a, b in itertools.pairwise(times)]
    positive_gaps = [gap for gap in gaps if gap > 0]
    if len(positive_gaps) < PAUSE_DETECTION_MIN_GAPS_FOR_MEDIAN:
        return PAUSE_DETECTION_THRESHOLD_SECONDS
    return max(
        PAUSE_DETECTION_THRESHOLD_SECONDS,
        PAUSE_DETECTION_SAMPLING_FACTOR * statistics.median(positive_gaps),
    )


def compute_moving_time_from_times(times: list[datetime]) -> float:
    """Compute moving time in seconds from ordered trackpoint timestamps.

    Sums the delta from the latest timestamp seen so far to each next one,
    skipping pause gaps (deltas above ``pause_threshold_seconds``, issue
    #571). Duplicate or out-of-order timestamps add nothing and do not
    become the baseline.

    Args:
        times: Trackpoint timestamps in recording order, without ``None``
            entries.

    Returns:
        Moving time in seconds. ``0.0`` if fewer than two timestamps.
    """
    if not times:
        return 0.0
    threshold = pause_threshold_seconds(times)
    moving_time = 0.0
    baseline = times[0]
    for time in times[1:]:
        delta = (time - baseline).total_seconds()
        if delta <= 0:
            continue
        if delta <= threshold:
            moving_time += delta
        baseline = time
    return moving_time
