"""Shared math for assembling an imported activity: lap generation, distance, pauses and power."""

import bisect
import itertools
import statistics
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

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
    """

    def __init__(self, waypoints: Sequence[Mapping[str, Any]]) -> None:
        """Parse every timestamp of the stream once.

        Args:
            waypoints: Waypoint dicts each containing a ``'time'`` key with an ISO 8601 string.
        """
        self.waypoints = waypoints
        self._times = [_parse_utc(wp["time"]) for wp in waypoints]
        self._ordered = all(a <= b for a, b in itertools.pairwise(self._times))

    def sum_between(self, start_time: str, end_time: str, keys: Sequence[str]) -> tuple[float, ...] | None:
        """Sum the named values of the waypoints whose time falls in (start_time, end_time].

        The lower bound is exclusive, so a sample on the boundary between two laps belongs to the earlier lap only and
        laps that follow one another partition the stream.

        Args:
            start_time: ISO 8601 exclusive lower bound.
            end_time: ISO 8601 inclusive upper bound.
            keys: The waypoint keys to sum.

        Returns:
            One sum per key; ``None`` when no sample falls in the window.
        """
        start_dt, end_dt = _parse_utc(start_time), _parse_utc(end_time)
        if self._ordered:
            indices: Iterable[int] = range(
                bisect.bisect_right(self._times, start_dt), bisect.bisect_right(self._times, end_dt)
            )
        else:
            indices = [i for i, time in enumerate(self._times) if start_dt < time <= end_dt]
        picked = [self.waypoints[i] for i in indices]
        if not picked:
            return None
        return tuple(sum(waypoint[key] for waypoint in picked) for key in keys)


def smooth_elevation_waypoints(ele_waypoints: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return an elevation stream with ``ele`` smoothed over time and the other keys unchanged.

    Args:
        ele_waypoints: Waypoints with an ISO 8601 ``time`` and a numeric ``ele`` in metres.

    Returns:
        New waypoints with the smoothed ``ele``; empty for an empty stream.
    """
    # The metric helpers live in this package's dependency-free computation module.
    import modules.activities.computation as activities_computation

    times = [_parse_utc(waypoint["time"]).timestamp() for waypoint in ele_waypoints]
    smoothed = activities_computation.smooth_elevation(times, [waypoint["ele"] for waypoint in ele_waypoints])
    return [{**waypoint, "ele": ele} for waypoint, ele in zip(ele_waypoints, smoothed, strict=True)]


def elevation_step_waypoints(ele_waypoints: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return the smoothed elevation stream with the gain and loss counted at each sample.

    The hysteresis runs once over the whole activity, so any lap's gain is the sum of its samples' ``gain`` and the
    laps add up to the activity's gain (see ``sum_lap_elevation``).

    Args:
        ele_waypoints: Waypoints with an ISO 8601 ``time`` and a numeric ``ele`` in metres.

    Returns:
        The smoothed waypoints, each with ``gain`` and ``loss`` in metres; empty for an empty stream.
    """
    # The metric helpers live in this package's dependency-free computation module.
    import modules.activities.computation as activities_computation

    smoothed = smooth_elevation_waypoints(ele_waypoints)
    gains, losses = activities_computation.elevation_steps([waypoint["ele"] for waypoint in smoothed])
    return [
        {**waypoint, "gain": gain, "loss": loss} for waypoint, gain, loss in zip(smoothed, gains, losses, strict=True)
    ]


def sum_lap_elevation(
    step_waypoints: Sequence[Mapping[str, Any]], start_time: str, end_time: str
) -> tuple[float, float] | None:
    """Return a lap's gain and loss from the activity's per-sample counts.

    The lap holds the samples in (``start_time``, ``end_time``]: a sample on the boundary between two laps counts
    in the earlier one, so laps that follow one another add up to the activity's gain and loss.

    Args:
        step_waypoints: The stream from ``elevation_step_waypoints``.
        start_time: ISO 8601 lap start (exclusive).
        end_time: ISO 8601 lap end (inclusive).

    Returns:
        The lap's (gain_m, loss_m); ``None`` when no sample falls within the lap.
    """
    sums = _TimedStream(step_waypoints).sum_between(start_time, end_time, ("gain", "loss"))
    return None if sums is None else (sums[0], sums[1])


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
