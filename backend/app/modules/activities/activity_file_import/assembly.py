"""Assemble the activities a file holds from its :class:`~modules.activities.activity_file_import.recording.Recording`.

One assembly serves every format: each session of a recording becomes one activity payload. The device's own totals win
wherever the file carries them; a value the file leaves out is computed from the samples with the shared math in
``computation`` and ``parser_utils``. The module is pure: it reads the recording and builds the payload, with no
logging, no database and no provider.
"""

import bisect
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import NotRequired, TypedDict
from zoneinfo import ZoneInfo

import core.timezone as core_timezone
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity_file_import.cleaning as activity_file_import_cleaning
import modules.activities.activity_file_import.parser_utils as activity_file_import_parser_utils
import modules.activities.activity_file_import.recording as activity_file_import_recording
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.activity_workout_steps.contracts as activity_workout_steps_contracts
import modules.activities.computation as activities_computation

#: The sport name FIT gives a lap-swimming session, whose working time comes from its lengths or split summaries.
_LAP_SWIMMING = "lap_swimming"

#: The name of a multisport activity the file and the caller leave unnamed.
_MULTISPORT_NAME = activity_constants.set_activity_name_based_on_activity_type(
    activity_constants.ActivityType.MULTISPORT.stored
)

#: The fewest sessions a multisport file needs to become a parent with legs.
_MIN_LEGS = 2

#: The FIT split type of a rest interval.
_REST_SPLIT = "interval_rest"


class ActivityFilePayload(TypedDict):
    """One assembled activity as the adapter takes it.

    Attributes:
        activity: The ingestion contract.
        is_elevation_set: Whether elevation data exists.
        ele_waypoints: Elevation waypoints.
        is_power_set: Whether power data exists.
        power_waypoints: Power waypoints.
        is_heart_rate_set: Whether heart-rate data exists.
        hr_waypoints: Heart-rate waypoints.
        is_velocity_set: Whether speed data exists (speed and pace share the flag).
        vel_waypoints: Speed waypoints.
        pace_waypoints: Pace waypoints.
        is_cadence_set: Whether cadence data exists.
        cad_waypoints: Cadence waypoints.
        is_lat_lon_set: Whether GPS data exists.
        lat_lon_waypoints: GPS waypoints.
        is_temperature_set: Whether temperature data exists.
        temp_waypoints: Temperature waypoints.
        laps: The activity's laps.
        sets: The workout sets; absent when the session has none.
        workout_steps: The planned workout steps; absent when the session has none.
    """

    activity: activity_contracts.ActivityCore
    is_elevation_set: bool
    ele_waypoints: list[activity_streams_contracts.ElevationWaypoint]
    is_power_set: bool
    power_waypoints: list[activity_streams_contracts.PowerWaypoint]
    is_heart_rate_set: bool
    hr_waypoints: list[activity_streams_contracts.HeartRateWaypoint]
    is_velocity_set: bool
    vel_waypoints: list[activity_streams_contracts.VelocityWaypoint]
    pace_waypoints: list[activity_streams_contracts.PaceWaypoint]
    is_cadence_set: bool
    cad_waypoints: list[activity_streams_contracts.CadenceWaypoint]
    is_lat_lon_set: bool
    lat_lon_waypoints: list[activity_streams_contracts.LatLonWaypoint]
    is_temperature_set: bool
    temp_waypoints: list[activity_streams_contracts.TemperatureWaypoint]
    laps: list[Mapping[str, object]]
    sets: NotRequired[list[list[object]]]
    workout_steps: NotRequired[list[activity_workout_steps_contracts.ActivityWorkoutStepsCreate]]


@dataclass(frozen=True, slots=True)
class AssembledFile:
    """What a recording assembles into: the activities of its sessions, under a parent when it is multisport.

    Attributes:
        parent: The multisport activity over the legs; ``None`` unless the recording is multisport with at least two
            sessions.
        activities: One payload per session, in time order; the legs when there is a parent.
    """

    parent: ActivityFilePayload | None
    activities: list[ActivityFilePayload]


@dataclass(frozen=True, slots=True)
class _Streams:
    """One session's waypoint streams, before any running-cadence conversion.

    Attributes:
        lat_lon: The positioned samples.
        segments: The position runs between breaks, each of at least two points.
        elevation: The altitude samples.
        heart_rate: The heart-rate samples.
        cadence: The cadence samples in the device's native unit.
        power: The power samples.
        temperature: The temperature samples.
        speed: The speed samples, the device's or derived from positions.
        pace: The pace samples, one for each speed above zero.
        measured_speed: The positions in ``speed`` of real measurements; ``None`` when every sample is one.
    """

    lat_lon: list[activity_streams_contracts.LatLonWaypoint]
    segments: list[list[activity_streams_contracts.LatLonWaypoint]]
    elevation: list[activity_streams_contracts.ElevationWaypoint]
    heart_rate: list[activity_streams_contracts.HeartRateWaypoint]
    cadence: list[activity_streams_contracts.CadenceWaypoint]
    power: list[activity_streams_contracts.PowerWaypoint]
    temperature: list[activity_streams_contracts.TemperatureWaypoint]
    speed: list[activity_streams_contracts.VelocityWaypoint]
    pace: list[activity_streams_contracts.PaceWaypoint]
    measured_speed: set[int] | None


def _tidy(value: float) -> float:
    """Return a whole number as an ``int`` so a stored stream reads ``85``, not ``85.0``.

    Args:
        value: The sample value.

    Returns:
        The value, an ``int`` when it is whole.
    """
    return int(value) if float(value).is_integer() else value


def _breaks(session: activity_file_import_recording.Session) -> frozenset[int]:
    """Return the samples where a new run of recording starts: after a device pause or a long gap in the clock.

    Args:
        session: The session.

    Returns:
        The sample indexes that start a run.
    """
    times = session.samples.time
    threshold = activity_file_import_parser_utils.pause_threshold_seconds(list(times))
    starts = {i for i in range(1, len(times)) if (times[i] - times[i - 1]).total_seconds() > threshold}
    for pause in session.pauses:
        resumed = bisect.bisect_left(times, pause.end)
        if 0 < resumed < len(times):
            starts.add(resumed)
    return frozenset(starts)


def _positions(
    samples: activity_file_import_recording.Samples, stamps: Sequence[str], breaks: frozenset[int]
) -> tuple[list[activity_streams_contracts.LatLonWaypoint], list[list[activity_streams_contracts.LatLonWaypoint]]]:
    """Collect the positioned samples and the position runs between breaks.

    Args:
        samples: The session's samples.
        stamps: The formatted time of each sample.
        breaks: The samples that start a run.

    Returns:
        The positioned samples, and the runs of at least two points.
    """
    lat_lon: list[activity_streams_contracts.LatLonWaypoint] = []
    segments: list[list[activity_streams_contracts.LatLonWaypoint]] = []
    run: list[activity_streams_contracts.LatLonWaypoint] = []
    for i, (lat, lon) in enumerate(zip(samples.lat, samples.lon, strict=True)):
        if i in breaks:
            if len(run) >= 2:
                segments.append(run)
            run = []
        if lat is not None and lon is not None:
            waypoint: activity_streams_contracts.LatLonWaypoint = {"time": stamps[i], "lat": lat, "lon": lon}
            lat_lon.append(waypoint)
            run.append(waypoint)
    if len(run) >= 2:
        segments.append(run)
    return lat_lon, segments


def _derived_speed(
    samples: activity_file_import_recording.Samples, stamps: Sequence[str], breaks: frozenset[int]
) -> tuple[list[activity_streams_contracts.VelocityWaypoint], set[int]]:
    """Derive speed from consecutive positioned samples.

    The first positioned sample after a break, and a sample whose clock did not advance, get a 0 placeholder; the
    returned positions mark the samples that are real measurements.

    Args:
        samples: The session's samples.
        stamps: The formatted time of each sample.
        breaks: The samples that start a run.

    Returns:
        The speed samples and the positions of the measured ones.
    """
    speed: list[activity_streams_contracts.VelocityWaypoint] = []
    measured: set[int] = set()
    prev_time: datetime | None = None
    prev_lat: float | None = None
    prev_lon: float | None = None
    for i, (time, lat, lon) in enumerate(zip(samples.time, samples.lat, samples.lon, strict=True)):
        if i in breaks:
            prev_time = prev_lat = prev_lon = None
        if lat is None or lon is None:
            continue
        if prev_time is not None and time > prev_time:
            measured.add(len(speed))
        speed.append(
            {
                "time": stamps[i],
                "vel": activities_computation.calculate_instant_speed(prev_time, time, lat, lon, prev_lat, prev_lon),
            }
        )
        if prev_time is None or time > prev_time:
            prev_time, prev_lat, prev_lon = time, lat, lon
    return speed, measured


def _build_streams(session: activity_file_import_recording.Session) -> _Streams:
    """Cut a session's sample table into waypoint streams.

    Args:
        session: The session.

    Returns:
        The streams; the speed is the device's when the session has any, else derived from positions.
    """
    samples = session.samples
    stamps = [core_timezone.format_utc(time) for time in samples.time]
    breaks = _breaks(session)
    lat_lon, segments = _positions(samples, stamps, breaks)
    speed: list[activity_streams_contracts.VelocityWaypoint]
    measured: set[int] | None
    if any(value is not None for value in samples.speed):
        speed = [{"time": s, "vel": v} for s, v in zip(stamps, samples.speed, strict=True) if v is not None]
        measured = None
    else:
        speed, measured = _derived_speed(samples, stamps, breaks)
    return _Streams(
        lat_lon=lat_lon,
        segments=segments,
        elevation=[{"time": s, "ele": v} for s, v in zip(stamps, samples.altitude, strict=True) if v is not None],
        heart_rate=[{"time": s, "hr": v} for s, v in zip(stamps, samples.heart_rate, strict=True) if v is not None],
        cadence=[{"time": s, "cad": _tidy(v)} for s, v in zip(stamps, samples.cadence, strict=True) if v is not None],
        power=[{"time": s, "power": v} for s, v in zip(stamps, samples.power, strict=True) if v is not None],
        temperature=[
            {"time": s, "temp": _tidy(v)} for s, v in zip(stamps, samples.temperature, strict=True) if v is not None
        ],
        speed=speed,
        pace=[{"time": w["time"], "pace": 1 / w["vel"]} for w in speed if w["vel"] > 0],
        measured_speed=measured,
    )


def _elapsed(session: activity_file_import_recording.Session) -> float:
    """Return a session's elapsed seconds: the device's, else from the start to the last sample.

    Args:
        session: The session.

    Returns:
        The elapsed seconds.
    """
    if session.summary.total_elapsed_time is not None:
        return session.summary.total_elapsed_time
    if not len(session.samples):
        return 0.0
    return max((session.samples.time[-1] - session.start_time).total_seconds(), 0.0)


def _timer_time(session: activity_file_import_recording.Session, elapsed: float) -> float:
    """Return a session's timed seconds: the device's, else the sum of its laps' timers, else the moving time.

    Args:
        session: The session.
        elapsed: The session's elapsed seconds.

    Returns:
        The timed seconds; the elapsed seconds when nothing else gives a positive time.
    """
    if session.summary.total_timer_time is not None:
        return session.summary.total_timer_time
    if session.summary.total_elapsed_time is not None:
        return session.summary.total_elapsed_time
    lap_timers = sum(lap.total_timer_time or 0.0 for lap in session.laps)
    if lap_timers > 0:
        return lap_timers
    moving = activity_file_import_parser_utils.compute_moving_time_from_times(list(session.samples.time))
    return moving if moving > 0 else elapsed


def _distance(session: activity_file_import_recording.Session, streams: _Streams, timer: float) -> float:
    """Return a session's distance in metres.

    Args:
        session: The session.
        streams: The session's streams.
        timer: The session's timed seconds.

    Returns:
        The device's distance, else the last distance sample, else the sum of the laps' distances, else the geodesic
        length of the position runs, else the average speed times the timer; ``0.0`` when none gives one.
    """
    if session.summary.distance:
        return session.summary.distance
    recorded = [value for value in session.samples.distance if value is not None]
    if recorded and recorded[-1]:
        return recorded[-1]
    if lap_distance := sum(lap.total_distance or 0.0 for lap in session.laps):
        return lap_distance
    walked = sum(
        activity_file_import_parser_utils.compute_distance_from_waypoints(segment) for segment in streams.segments
    )
    if walked:
        return walked
    if session.summary.avg_speed and timer:
        return session.summary.avg_speed * timer
    return 0.0


def _active_time(session: activity_file_import_recording.Session, distance: float, timer: float) -> float:
    """Return the seconds a pace is measured over: a lap swimmer's working time, else the timer.

    Args:
        session: The session.
        distance: The session's distance in metres.
        timer: The session's timed seconds.

    Returns:
        The seconds from the pool lengths or, without them, the split summaries; the timer otherwise.
    """
    if not distance or session.sport != _LAP_SWIMMING:
        return timer
    if session.lengths:
        return sum((length.total_timer_time or 0.0) for length in session.lengths if length.length_type == "active")
    if session.split_summaries:
        return sum(
            split.total_timer_time
            for split in session.split_summaries
            if split.split_type != _REST_SPLIT and split.total_timer_time is not None
        )
    return timer


def _timezone_from_offset(offset_seconds: int, reference_date: datetime, athlete_timezone: str) -> str:
    """Name the timezone of a GPS-less session that reports a UTC offset.

    The athlete's own zone wins when it agrees with the recorded offset, because an offset is not a timezone and a
    fixed-offset name would ignore daylight saving; otherwise the device's offset is the better evidence of where the
    athlete was.

    Args:
        offset_seconds: The UTC offset the file reports, in seconds.
        reference_date: The instant the offset was observed at.
        athlete_timezone: The owner's configured IANA timezone.

    Returns:
        An IANA timezone name.
    """
    try:
        athlete_offset = reference_date.astimezone(ZoneInfo(athlete_timezone)).utcoffset()
    except ValueError, KeyError:
        athlete_offset = None
    if athlete_offset is not None and athlete_offset.total_seconds() == offset_seconds:
        return athlete_timezone
    return _find_timezone_name(offset_seconds, reference_date) or athlete_timezone


def _find_timezone_name(offset_seconds: int, reference_date: datetime) -> str | None:
    """Name a timezone for a bare UTC offset.

    A fixed-offset ``Etc/GMT`` zone is preferred because it encodes exactly what the device said; an offset that is not
    a whole number of hours falls back to the first zone, in sorted order, that has it on the reference date.

    Args:
        offset_seconds: The UTC offset, in seconds.
        reference_date: The instant the offset was observed at.

    Returns:
        An IANA timezone name, or ``None`` when no zone has the offset.
    """
    if offset_seconds % 3600 == 0:
        hours = offset_seconds // 3600
        if -12 <= hours <= 14:
            # POSIX-style inverted sign: Etc/GMT-9 is UTC+9.
            candidate = f"Etc/GMT{-hours:+d}" if hours != 0 else "UTC"
            if candidate == "UTC" or candidate in core_timezone.known_names():
                return candidate
    for name in core_timezone.known_names_sorted():
        offset = reference_date.astimezone(ZoneInfo(name)).utcoffset()
        if offset is not None and offset.total_seconds() == offset_seconds:
            return name
    return None


def _timezone(
    recording: activity_file_import_recording.Recording,
    session: activity_file_import_recording.Session,
    activity_type: int,
    streams: _Streams,
    default_timezone: str,
) -> str:
    """Resolve the timezone a session was recorded in.

    Args:
        recording: The recording.
        session: The session.
        activity_type: The session's activity type.
        streams: The session's streams.
        default_timezone: The owner's timezone, used when the file yields none.

    Returns:
        A virtual activity keeps the default; otherwise the first position's zone, else the device's UTC offset
        (the ``activity`` message's before the ``device_settings`` one), else the default.
    """
    if activity_type in activity_constants.VIRTUAL_ACTIVITY_TYPES:
        return default_timezone
    if streams.lat_lon:
        first = streams.lat_lon[0]
        return activity_file_import_parser_utils.resolve_timezone_from_lat_lon(
            first["lat"], first["lon"], default_timezone
        )
    local, device = recording.local_time_offset, recording.device_time_offset
    # Some writers set the local timestamp equal to the UTC one when the zone is unknown, so a 0 yields to a device
    # offset.
    if local is not None and (local != 0 or not device):
        return _timezone_from_offset(local, session.start_time, default_timezone)
    if device:
        return _timezone_from_offset(device, session.start_time, default_timezone)
    return default_timezone


def _heart_rate(session: activity_file_import_recording.Session, streams: _Streams) -> tuple[int | None, int | None]:
    """Return a session's average and maximum heart rate.

    Args:
        session: The session.
        streams: The session's streams.

    Returns:
        The values recomputed from the samples without zeros (a zero means a lost sensor) when there are any, else the
        device's.
    """
    avg, peak = session.summary.avg_heart_rate, session.summary.max_heart_rate
    if streams.heart_rate:
        sampled_avg, sampled_max = activities_computation.calculate_avg_and_max(streams.heart_rate, "hr")
        avg = round(sampled_avg) if sampled_avg else avg
        peak = round(sampled_max) if sampled_max else peak
    return avg, peak


def _power(
    session: activity_file_import_recording.Session, streams: _Streams
) -> tuple[int | None, int | None, int | None]:
    """Return a session's average, maximum and normalized power.

    Args:
        session: The session.
        streams: The session's streams.

    Returns:
        The device's values, with a missing one computed from the samples.
    """
    avg: float | None = session.summary.avg_power
    peak: float | None = session.summary.max_power
    normalized: float | None = session.summary.normalized_power
    if streams.power and (avg is None or normalized is None):
        sampled_avg, sampled_max, sampled_np = activity_file_import_parser_utils.calculate_power_metrics(streams.power)
        if avg is None:
            avg, peak = sampled_avg, sampled_max
        if normalized is None:
            normalized = sampled_np
    return (
        round(avg) if avg else None,
        round(peak) if peak else None,
        round(normalized) if normalized else None,
    )


def _cadence_stat(summary_value: float | None, fraction: float | None, sampled: float, running: bool) -> int | None:
    """Return one cadence statistic in the unit the activity stores.

    Args:
        summary_value: The device's whole-number value, or ``None``.
        fraction: The device's fractional part.
        sampled: The value computed from the samples, ``0`` when there are none.
        running: Whether the activity is a running type, stored as steps per minute.

    Returns:
        The device's value when it is not zero, else the sampled one; doubled for running.
    """
    value = summary_value
    if not value and sampled:
        value, fraction = sampled, None
    if running:
        return activities_computation.double_running_cadence(value, fraction)
    return round(value) if value is not None else None


def _cadence(
    session: activity_file_import_recording.Session, streams: _Streams, running: bool
) -> tuple[int | None, int | None]:
    """Return a session's average and maximum cadence.

    Args:
        session: The session.
        streams: The session's streams, in the device's native cadence unit.
        running: Whether the activity is a running type.

    Returns:
        The device's values, with a missing or zero one computed from the samples; steps per minute for running.
    """
    summary = session.summary
    sampled_avg, sampled_max = (
        activities_computation.calculate_avg_and_max(streams.cadence, "cad") if streams.cadence else (0, 0)
    )
    return (
        _cadence_stat(summary.avg_cadence, summary.avg_fractional_cadence, sampled_avg, running),
        _cadence_stat(summary.max_cadence, summary.max_fractional_cadence, sampled_max, running),
    )


def _elevation(session: activity_file_import_recording.Session, streams: _Streams) -> tuple[int | None, int | None]:
    """Return a session's elevation gain and loss in metres.

    Args:
        session: The session.
        streams: The session's streams.

    Returns:
        The device's values, with a missing one computed from the smoothed altitude samples.
    """
    gain, loss = session.summary.total_ascent, session.summary.total_descent
    if (gain is None or loss is None) and streams.elevation:
        computed_gain, computed_loss = activities_computation.compute_elevation_gain_and_loss(streams.elevation)
        # A computed 0 m on a flat ride is a real value, not missing data.
        if gain is None and computed_gain is not None:
            gain = round(computed_gain)
        if loss is None and computed_loss is not None:
            loss = round(computed_loss)
    return gain, loss


def _speeds(
    session: activity_file_import_recording.Session, streams: _Streams, distance: float, pace: float | None
) -> tuple[float | None, float | None]:
    """Return a session's average and maximum speed in metres per second.

    Args:
        session: The session.
        streams: The session's streams.
        distance: The session's distance in metres.
        pace: The session's pace in seconds per metre.

    Returns:
        The device's values; otherwise the average is the inverse of the pace and the maximum is the robust maximum of
        the measured speed samples. Both are ``None`` without a distance.
    """
    if not distance:
        # A device writes an average speed of 0 for a session that covers no distance (strength, HIIT).
        return None, None
    avg, peak = session.summary.avg_speed, session.summary.max_speed
    if avg is None and pace:
        avg = 1 / pace
    if peak is None:
        measured = activity_file_import_parser_utils.measured_speed_samples(streams.speed, streams.measured_speed)
        peak = activities_computation.calculate_robust_max([sample["vel"] for sample in measured]) or None
    return avg, peak


def _lap_window(session: activity_file_import_recording.Session, index: int) -> tuple[datetime, float]:
    """Return a device lap's start and elapsed seconds.

    Args:
        session: The session.
        index: The lap's position.

    Returns:
        The lap's start and the device's elapsed seconds; without them the time to the next lap's start (the last lap
        to the last sample), else the lap's timer.
    """
    lap = session.laps[index]
    if lap.total_elapsed_time is not None:
        return lap.start_time, lap.total_elapsed_time
    following = session.laps[index + 1].start_time if index + 1 < len(session.laps) else None
    end = following or (session.samples.time[-1] if len(session.samples) else None)
    if end is not None and end > lap.start_time:
        return lap.start_time, (end - lap.start_time).total_seconds()
    return lap.start_time, lap.total_timer_time or 0.0


@dataclass(frozen=True, slots=True)
class _LapSamples:
    """What a lap's own samples say, for the statistics its device message leaves out.

    Attributes:
        avg_hr: Average heart rate without zeros.
        max_hr: Maximum heart rate.
        avg_cad: Average cadence as stored (steps per minute for running).
        max_cad: Maximum cadence as stored.
        avg_power: Average power.
        max_power: Maximum power.
        normalized_power: Normalized power.
        max_speed: Highest device speed.
        start: Latitude and longitude of the first positioned sample.
        end: Latitude and longitude of the last positioned sample.
    """

    avg_hr: int | None
    max_hr: int | None
    avg_cad: int | None
    max_cad: int | None
    avg_power: int | None
    max_power: int | None
    normalized_power: int | None
    max_speed: float | None
    start: tuple[float | None, float | None]
    end: tuple[float | None, float | None]


def _sampled_lap(window: activity_file_import_recording.Samples, running: bool) -> _LapSamples:
    """Compute a lap's statistics from the samples inside it.

    Args:
        window: The samples inside the lap.
        running: Whether the activity is a running type.

    Returns:
        The statistics; ``None`` where the lap has no samples of the channel or the value is zero.
    """
    hr = [{"hr": v} for v in window.heart_rate if v is not None]
    avg_hr, max_hr = activities_computation.calculate_avg_and_max(hr, "hr") if hr else (0, 0)
    cad = [{"cad": v} for v in window.cadence if v is not None]
    avg_cad, max_cad = activities_computation.calculate_avg_and_max(cad, "cad") if cad else (0, 0)
    power = [{"power": v} for v in window.power if v is not None]
    avg_power, max_power, normalized_power = (
        activity_file_import_parser_utils.calculate_power_metrics(power) if power else (None, None, None)
    )
    speeds = [v for v in window.speed if v is not None]
    positions = [(lat, lon) for lat, lon in zip(window.lat, window.lon, strict=True) if lat is not None]
    return _LapSamples(
        avg_hr=round(avg_hr) if avg_hr else None,
        max_hr=round(max_hr) if max_hr else None,
        avg_cad=_cadence_stat(None, None, avg_cad, running),
        max_cad=_cadence_stat(None, None, max_cad, running),
        avg_power=round(avg_power) if avg_power else None,
        max_power=round(max_power) if max_power else None,
        normalized_power=round(normalized_power) if normalized_power else None,
        max_speed=max(speeds) if speeds else None,
        start=positions[0] if positions else (None, None),
        end=positions[-1] if positions else (None, None),
    )


def _first[T](device: T | None, sampled: T | None) -> T | None:
    """Return the device's value, else the one computed from the samples.

    Args:
        device: The value the device reported, ``None`` when it left it out.
        sampled: The value computed from the samples.

    Returns:
        The device's value unless it is ``None``, a genuine 0 included.
    """
    return device if device is not None else sampled


def _lap_speed(lap: activity_file_import_recording.Lap) -> tuple[float | None, float | None]:
    """Return a device lap's average and maximum speed in metres per second.

    Args:
        lap: The lap.

    Returns:
        The device's speeds; the average falls back to the lap's distance over its timer.
    """
    avg = lap.avg_speed
    if not avg and lap.total_distance and lap.total_timer_time:
        avg = lap.total_distance / lap.total_timer_time
    # A speed of 0 carries no pace, so it is stored as missing.
    return avg or None, lap.max_speed or None


def _device_lap(
    lap: activity_file_import_recording.Lap,
    start: datetime,
    elapsed: float,
    session: activity_file_import_recording.Session,
    running: bool,
    last: bool,
) -> dict[str, object]:
    """Map a device lap to the row a stored lap has.

    Args:
        lap: The lap.
        start: The lap's start.
        elapsed: The lap's elapsed seconds.
        session: The session the lap belongs to.
        running: Whether the activity is a running type.
        last: Whether it is the session's last lap.

    Returns:
        The lap row; a statistic the device left out is computed from the samples inside the lap, and running cadence
        is stored as steps per minute with the fractional columns cleared.
    """
    # A sample on the instant one lap ends and the next starts belongs to the later lap; the last lap keeps its end.
    end = start + timedelta(seconds=elapsed, microseconds=1 if last else 0)
    window = activity_file_import_recording.samples_between(session.samples, start, end)
    sampled = _sampled_lap(window, running)
    avg_speed, max_speed = _lap_speed(lap)
    max_speed = max_speed or sampled.max_speed or None
    if running:
        avg_cadence = activities_computation.double_running_cadence(lap.avg_cadence, lap.avg_fractional_cadence)
        max_cadence = activities_computation.double_running_cadence(lap.max_cadence, lap.max_fractional_cadence)
        fractions: tuple[float | None, float | None] = (None, None)
    else:
        avg_cadence, max_cadence = lap.avg_cadence, lap.max_cadence
        fractions = (lap.avg_fractional_cadence, lap.max_fractional_cadence)
    return {
        "start_time": start,
        "start_position_lat": _first(lap.start_position_lat, sampled.start[0]),
        "start_position_long": _first(lap.start_position_long, sampled.start[1]),
        "end_position_lat": _first(lap.end_position_lat, sampled.end[0]),
        "end_position_long": _first(lap.end_position_long, sampled.end[1]),
        "total_elapsed_time": elapsed,
        "total_timer_time": lap.total_timer_time if lap.total_timer_time is not None else elapsed,
        "total_distance": lap.total_distance,
        "total_cycles": lap.total_cycles,
        "total_calories": lap.total_calories,
        "avg_heart_rate": _first(lap.avg_heart_rate, sampled.avg_hr),
        "max_heart_rate": _first(lap.max_heart_rate, sampled.max_hr),
        "avg_cadence": _first(avg_cadence, sampled.avg_cad),
        "max_cadence": _first(max_cadence, sampled.max_cad),
        "avg_power": _first(lap.avg_power, sampled.avg_power),
        "max_power": _first(lap.max_power, sampled.max_power),
        "total_ascent": lap.total_ascent,
        "total_descent": lap.total_descent,
        "intensity": lap.intensity,
        "lap_trigger": lap.lap_trigger,
        "sport": lap.sport,
        "sub_sport": lap.sub_sport,
        "normalized_power": _first(lap.normalized_power, sampled.normalized_power),
        "total_work": lap.total_work,
        "avg_vertical_oscillation": lap.avg_vertical_oscillation,
        "avg_stance_time": lap.avg_stance_time,
        "avg_fractional_cadence": fractions[0],
        "max_fractional_cadence": fractions[1],
        "enhanced_avg_speed": avg_speed,
        "enhanced_max_speed": max_speed,
        "enhanced_avg_pace": 1 / avg_speed if avg_speed else None,
        "enhanced_max_pace": 1 / max_speed if max_speed else None,
        "enhanced_min_altitude": lap.min_altitude,
        "enhanced_max_altitude": lap.max_altitude,
        "avg_vertical_ratio": lap.avg_vertical_ratio,
        "avg_step_length": lap.avg_step_length,
    }


def _fill_lap_elevation(laps: list[dict[str, object]], elevation: Sequence[Mapping[str, object]]) -> None:
    """Fill the ascent and descent a device left out of its laps.

    Some exporters omit them from lap messages. They are summed from the once-smoothed altitude stream, so the laps
    partition the activity's own gain and loss; a value the device reported, even a genuine 0, is never replaced.

    Args:
        laps: The lap rows; updated in place.
        elevation: The session's altitude waypoints.
    """
    missing = [lap for lap in laps if lap["total_ascent"] is None or lap["total_descent"] is None]
    if not missing or not elevation:
        return
    smoothed = activities_computation.smooth_elevation_stream(elevation)
    for lap in missing:
        start = lap["start_time"]
        elapsed = lap["total_elapsed_time"]
        if not isinstance(start, datetime) or not isinstance(elapsed, int | float):
            continue
        sliced = activity_file_import_parser_utils.slice_lap_elevation(
            smoothed,
            core_timezone.format_utc(start),
            core_timezone.format_utc(start + timedelta(seconds=elapsed)),
        )
        if not sliced:
            continue
        gain, loss = activities_computation.sum_elevation_deltas(sliced)
        if lap["total_ascent"] is None:
            lap["total_ascent"] = round(gain)
        if lap["total_descent"] is None:
            lap["total_descent"] = round(loss)


def _laps(
    session: activity_file_import_recording.Session,
    streams: _Streams,
    cadence: list[activity_streams_contracts.CadenceWaypoint],
    running: bool,
    lap_distance_km: float,
) -> list[Mapping[str, object]]:
    """Build a session's laps: the device's when it recorded any, else one per ``lap_distance_km`` of each run.

    Args:
        session: The session.
        streams: The session's streams.
        cadence: The cadence waypoints as stored (steps per minute for running).
        running: Whether the activity is a running type.
        lap_distance_km: Distance after which a generated lap closes.

    Returns:
        The lap rows in time order.
    """
    if session.laps:
        rows = [
            _device_lap(lap, *_lap_window(session, i), session, running, i == len(session.laps) - 1)
            for i, lap in enumerate(session.laps)
        ]
        _fill_lap_elevation(rows, streams.elevation)
        return list(rows)
    smoothed = activities_computation.smooth_elevation_stream(streams.elevation)
    generated: list[Mapping[str, object]] = []
    for segment in streams.segments:
        generated.extend(
            activity_file_import_parser_utils.generate_activity_laps(
                segment,
                streams.elevation,
                streams.power,
                streams.heart_rate,
                cadence,
                streams.speed,
                distance_per_lap_km=lap_distance_km,
                measured_vel_indices=streams.measured_speed,
                smoothed_ele_waypoints=smoothed,
            )
        )
    return generated


def _name(
    recording: activity_file_import_recording.Recording,
    activity_name: str | None,
    default: str = activity_constants.DEFAULT_ACTIVITY_NAME,
) -> str:
    """Pick the activity's name: the caller's, else the file's, else the default.

    Args:
        recording: The recording.
        activity_name: The name the caller gave, if any.
        default: The name when neither the caller nor the file gives one.

    Returns:
        The name.
    """
    if activity_name:
        return activity_name
    if recording.name and recording.name != activity_constants.DEFAULT_ACTIVITY_NAME:
        return recording.name
    return default


def _assemble_session(
    recording: activity_file_import_recording.Recording,
    session: activity_file_import_recording.Session,
    user_id: uuid.UUID,
    activity_name: str | None,
    default_timezone: str,
    lap_distance_km: float,
    *,
    is_leg: bool,
) -> ActivityFilePayload:
    """Assemble one session into an activity payload.

    Args:
        recording: The recording the session belongs to.
        session: The session.
        user_id: ID of the user the activity belongs to.
        activity_name: The name the caller gave, if any.
        default_timezone: The owner's timezone, used when the file yields none.
        lap_distance_km: Distance after which a generated lap closes.
        is_leg: Whether the session is a leg of a multisport parent, which is named for its sport.

    Returns:
        The payload.
    """
    summary = session.summary
    streams = _build_streams(session)
    activity_type = activity_constants.define_activity_type(session.sport) if session.sport else 10
    running = activity_constants.is_running_cadence_type(activity_type)

    elapsed = _elapsed(session)
    timer = _timer_time(session, elapsed)
    distance = _distance(session, streams, timer)
    active_time = _active_time(session, distance, timer)
    pace = activities_computation.calculate_pace_from_duration(distance, active_time) or None
    avg_speed, max_speed = _speeds(session, streams, distance, pace)
    avg_hr, max_hr = _heart_rate(session, streams)
    avg_power, max_power, normalized_power = _power(session, streams)
    avg_cadence, max_cadence = _cadence(session, streams, running)
    elevation_gain, elevation_loss = _elevation(session, streams)

    cadence = activities_computation.double_cadence_waypoints(streams.cadence) if running else streams.cadence
    laps = _laps(session, streams, cadence, running, lap_distance_km)

    stored_type = activity_constants.ActivityType.from_stored(activity_type)
    activity = activity_contracts.ActivityCore(
        user_id=user_id,
        name=stored_type.label if is_leg else _name(recording, activity_name),
        description=recording.description,
        distance=round(distance) if distance else 0,
        activity_type=stored_type,
        start_time=core_timezone.to_utc_second(session.start_time),
        end_time=core_timezone.to_utc_second(session.start_time + timedelta(seconds=elapsed)),
        timezone=_timezone(recording, session, activity_type, streams, default_timezone),
        total_elapsed_time=elapsed,
        total_timer_time=active_time,
        elevation_gain=elevation_gain,
        elevation_loss=elevation_loss,
        pace=pace,
        average_speed=avg_speed,
        max_speed=max_speed,
        average_power=avg_power,
        max_power=max_power,
        normalized_power=normalized_power,
        average_hr=avg_hr,
        max_hr=max_hr,
        average_cad=avg_cadence,
        max_cad=max_cadence,
        workout_feeling=summary.workout_feeling,
        workout_rpe=summary.workout_rpe,
        calories=summary.calories,
        tracker_manufacturer=recording.manufacturer,
        tracker_model=recording.product,
        total_cycles=summary.total_cycles,
    )
    payload: ActivityFilePayload = {
        "activity": activity,
        "is_elevation_set": bool(streams.elevation),
        "ele_waypoints": streams.elevation,
        "is_power_set": bool(streams.power),
        "power_waypoints": streams.power,
        "is_heart_rate_set": bool(streams.heart_rate),
        "hr_waypoints": streams.heart_rate,
        "is_velocity_set": bool(streams.speed),
        "vel_waypoints": streams.speed,
        "pace_waypoints": streams.pace,
        "is_cadence_set": bool(cadence),
        "cad_waypoints": cadence,
        "is_lat_lon_set": bool(streams.lat_lon),
        "lat_lon_waypoints": streams.lat_lon,
        "is_temperature_set": bool(streams.temperature),
        "temp_waypoints": streams.temperature,
        "laps": laps,
    }
    if session.sets:
        payload["sets"] = list(session.sets)
    if session.workout_steps:
        payload["workout_steps"] = list(session.workout_steps)
    return payload


def _sum_or_none(values: Iterable[int | None]) -> int | None:
    """Add up the values a total is made of.

    Args:
        values: The legs' values, ``None`` for a leg that has none.

    Returns:
        The sum of the values that exist; ``None`` when none does.
    """
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _max_or_none(values: Iterable[int | None]) -> int | None:
    """Return the largest value that exists.

    Args:
        values: The legs' values, ``None`` for a leg that has none.

    Returns:
        The largest value; ``None`` when none exists.
    """
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _timer_weighted_average(legs: Sequence[activity_contracts.ActivityCore], field: str) -> int | None:
    """Average a leg field over the legs that have it, each weighted by its timer time.

    Args:
        legs: The legs' activities.
        field: The name of the field to average.

    Returns:
        The rounded average; ``None`` when no leg has the field.
    """
    pairs = [(getattr(leg, field), leg.total_timer_time or 0.0) for leg in legs if getattr(leg, field) is not None]
    if not pairs:
        return None
    weight = sum(timer for _, timer in pairs)
    if weight <= 0:
        return round(sum(value for value, _ in pairs) / len(pairs))
    return round(sum(value * timer for value, timer in pairs) / weight)


def _assemble_parent(
    recording: activity_file_import_recording.Recording,
    legs: Sequence[ActivityFilePayload],
    user_id: uuid.UUID,
    activity_name: str | None,
) -> ActivityFilePayload:
    """Assemble the multisport activity over a recording's legs.

    Args:
        recording: The recording.
        legs: The assembled legs, in time order.
        user_id: ID of the user the activity belongs to.
        activity_name: The name the caller gave, if any.

    Returns:
        The parent payload: the legs' totals and no streams, laps, sets or workout steps.
    """
    activities = [leg["activity"] for leg in legs]
    first, last = activities[0], activities[-1]
    start = first.start_time
    end = last.end_time
    timer = (
        recording.timer_time
        if recording.timer_time is not None
        else sum(leg.total_timer_time or 0.0 for leg in activities)
    )
    # A FIT session starts on a whole second, so back-to-back legs overlap by a fraction of one and their span can
    # fall short of the timer; the elapsed time is never less than the time the device timed.
    elapsed = max((end - start).total_seconds(), timer)
    activity = activity_contracts.ActivityCore(
        user_id=user_id,
        name=_name(recording, activity_name, _MULTISPORT_NAME),
        description=recording.description,
        distance=sum(leg.distance for leg in activities),
        activity_type=activity_constants.ActivityType.MULTISPORT,
        start_time=start,
        end_time=end,
        timezone=first.timezone,
        total_elapsed_time=elapsed,
        total_timer_time=timer,
        elevation_gain=_sum_or_none(leg.elevation_gain for leg in activities),
        elevation_loss=_sum_or_none(leg.elevation_loss for leg in activities),
        average_power=_timer_weighted_average(activities, "average_power"),
        max_power=_max_or_none(leg.max_power for leg in activities),
        average_hr=_timer_weighted_average(activities, "average_hr"),
        max_hr=_max_or_none(leg.max_hr for leg in activities),
        calories=_sum_or_none(leg.calories for leg in activities),
        tracker_manufacturer=recording.manufacturer,
        tracker_model=recording.product,
    )
    return {
        "activity": activity,
        "is_elevation_set": False,
        "ele_waypoints": [],
        "is_power_set": False,
        "power_waypoints": [],
        "is_heart_rate_set": False,
        "hr_waypoints": [],
        "is_velocity_set": False,
        "vel_waypoints": [],
        "pace_waypoints": [],
        "is_cadence_set": False,
        "cad_waypoints": [],
        "is_lat_lon_set": False,
        "lat_lon_waypoints": [],
        "is_temperature_set": False,
        "temp_waypoints": [],
        "laps": [],
    }


def assemble(
    recording: activity_file_import_recording.Recording,
    user_id: uuid.UUID,
    activity_name: str | None,
    default_timezone: str,
    lap_distance_km: float,
) -> AssembledFile:
    """Assemble the activities of a recording, one per session, under a parent when it is multisport.

    Each session is cleaned first, see ``cleaning``. Privacy defaults, gear and provider ids are attached later by
    the ``activity_ingestion`` enrichment seam.

    Args:
        recording: The decoded file.
        user_id: ID of the user the activities belong to.
        activity_name: The name the caller gave; the file's name, or the default, when ``None``.
        default_timezone: The owner's IANA timezone, used only when the file yields none of its own.
        lap_distance_km: Distance after which a generated lap closes, for a session with no device laps.

    Returns:
        The activities of the sessions in time order, and the multisport parent when the recording is multisport with
        at least two sessions.
    """
    grouped = recording.multisport and len(recording.sessions) >= _MIN_LEGS
    activities = [
        _assemble_session(
            recording,
            activity_file_import_cleaning.clean_session(session),
            user_id,
            activity_name,
            default_timezone,
            lap_distance_km,
            is_leg=grouped,
        )
        for session in recording.sessions
    ]
    parent = _assemble_parent(recording, activities, user_id, activity_name) if grouped else None
    return AssembledFile(parent=parent, activities=activities)
