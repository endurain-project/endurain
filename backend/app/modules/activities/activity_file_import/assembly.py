"""Assemble the activities a file holds from its :class:`~modules.activities.activity_file_import.recording.Recording`.

One assembly serves every format: each session of a recording becomes one activity payload. The device's own totals win
wherever the file carries them; a value the file leaves out is computed from the samples with the shared math in
``computation`` and ``parser_utils``. The module is pure: it reads the recording and builds the payload, with no
logging, no database and no provider.
"""

import bisect
import dataclasses
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
import modules.activities.activity_streams.constants as activity_streams_constants
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
        samples: The session's columnar samples on one timeline; ``None`` when it has no sample with a value.
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
    samples: activity_streams_contracts.ParsedSamples | None
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
        step_speed: The measured speed of the step ending at each of the session's samples, the device's when it
            recorded any; ``None`` where a sample has none.
        sample_speed: The speed that decides whether each sample is moving: ``step_speed`` for a device speed, else the
            lower of the step's and the straight-line speed over a window around it.
        speed_samples: The value of the ``speed`` stream at each of the session's samples; ``None`` where the stream
            has no point.
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
    step_speed: list[float | None]
    sample_speed: list[float | None]
    speed_samples: list[float | None]


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
    threshold = activities_computation.pause_threshold_seconds(list(times))
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
) -> tuple[list[activity_streams_contracts.VelocityWaypoint], set[int], list[float | None]]:
    """Derive speed from consecutive positioned samples, over the real time between them.

    The first positioned sample after a break, and a sample whose clock did not advance, get a 0 placeholder; the
    returned positions mark the samples that are real measurements.

    Args:
        samples: The session's samples.
        stamps: The formatted time of each sample.
        breaks: The samples that start a run.

    Returns:
        The speed samples, the positions of the measured ones, and the measured speed at each sample of the session
        (``None`` for the placeholders and the samples without a position).
    """
    speed: list[activity_streams_contracts.VelocityWaypoint] = []
    measured: set[int] = set()
    by_sample: list[float | None] = [None] * len(samples.time)
    prev_time: datetime | None = None
    prev_lat: float | None = None
    prev_lon: float | None = None
    for i, (time, lat, lon) in enumerate(zip(samples.time, samples.lat, samples.lon, strict=True)):
        if i in breaks:
            prev_time = prev_lat = prev_lon = None
        if lat is None or lon is None:
            continue
        vel = activities_computation.calculate_step_speed(prev_time, time, lat, lon, prev_lat, prev_lon)
        if prev_time is not None and time > prev_time:
            measured.add(len(speed))
            by_sample[i] = vel
        speed.append({"time": stamps[i], "vel": vel})
        if prev_time is None or time > prev_time:
            prev_time, prev_lat, prev_lon = time, lat, lon
    return speed, measured, by_sample


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
        step_speed = list(samples.speed)
        by_sample = step_speed
        speed_samples = step_speed
    else:
        speed, measured, step_speed = _derived_speed(samples, stamps, breaks)
        # A sample moves when both its last second and the distance covered over a window around it are fast enough:
        # GPS jitter at a stop makes each step fast but covers no distance, a window alone blurs a clean stop, and a
        # sub-second step alone can be 0 between two fixes of the same position.
        seconds = [time.timestamp() for time in samples.time]
        trailing = activities_computation.trailing_speeds(seconds, samples.lat, samples.lon, breaks)
        window_speed = activities_computation.displacement_speeds(seconds, samples.lat, samples.lon, breaks)
        by_sample = [
            None if step is None or window is None else min(step, window)
            for step, window in zip(trailing, window_speed, strict=True)
        ]
        # The derived speed has a point at every positioned sample, in order.
        speed_samples = [None] * len(samples.time)
        positioned = (
            i
            for i, (lat, lon) in enumerate(zip(samples.lat, samples.lon, strict=True))
            if lat is not None and lon is not None
        )
        for i, waypoint in zip(positioned, speed, strict=True):
            speed_samples[i] = waypoint["vel"]
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
        step_speed=step_speed,
        sample_speed=by_sample,
        speed_samples=speed_samples,
    )


def _millis_since(start: datetime, time: datetime) -> int:
    """Return the milliseconds from ``start`` to ``time``, cut to the whole millisecond.

    The cut is a floor, so the whole second of ``start + offset`` is the second a waypoint stamped from ``time`` has.

    Args:
        start: The activity's start, whole seconds, timezone-aware UTC.
        time: A sample's time, timezone-aware UTC.

    Returns:
        The offset, negative for a sample before the start.
    """
    delta = time - start
    return (delta.days * 86400 + delta.seconds) * 1000 + delta.microseconds // 1000


def _channel(values: Iterable[float | None]) -> list[float | None] | None:
    """Return a channel's values, or ``None`` when no sample has one.

    Args:
        values: The channel's value at each sample.

    Returns:
        The values, or ``None`` when every one is ``None``.
    """
    channel: list[float | None] = list(values)
    return channel if any(value is not None for value in channel) else None


def _smoothed_altitude(samples: activity_file_import_recording.Samples) -> list[float | None]:
    """Return the altitude column smoothed over time, as the elevation stream stores it.

    The smoothing reads the samples that have an altitude, each at its whole second, like the stream's waypoints.

    Args:
        samples: The session's samples.

    Returns:
        The smoothed altitude at each sample, ``None`` where the sample has none.
    """
    present = [
        (i, time.replace(microsecond=0).timestamp(), altitude)
        for i, (time, altitude) in enumerate(zip(samples.time, samples.altitude, strict=True))
        if altitude is not None
    ]
    smoothed = activities_computation.smooth_elevation([t for _, t, _ in present], [a for _, _, a in present])
    column: list[float | None] = [None] * len(samples.time)
    for (i, _, _), altitude in zip(present, smoothed, strict=True):
        column[i] = altitude
    return column


def _build_samples(
    session: activity_file_import_recording.Session, streams: _Streams, start: datetime, *, running: bool
) -> activity_streams_contracts.ParsedSamples | None:
    """Cut a session's sample table into the columnar samples, with the values its waypoint streams store.

    Elevation is the smoothed series, running cadence is in steps per minute, speed is the ``speed`` stream's and a
    position needs both coordinates. A heart rate the cleaning dropped is ``None``.

    Args:
        session: The cleaned session.
        streams: The session's waypoint streams.
        start: The activity's start, whole seconds, timezone-aware UTC.
        running: Whether the session's cadence is a single leg's rate, doubled to steps per minute.

    Returns:
        The samples, or ``None`` when no sample has a value on any channel.
    """
    samples = session.samples
    positioned = [lat is not None and lon is not None for lat, lon in zip(samples.lat, samples.lon, strict=True)]
    latitude = _channel(
        lat if has_position else None for lat, has_position in zip(samples.lat, positioned, strict=True)
    )
    longitude = _channel(
        lon if has_position else None for lon, has_position in zip(samples.lon, positioned, strict=True)
    )
    # Running cadence mirrors ``double_cadence_waypoints``.
    cadence = _channel(None if value is None else round(value * 2) if running else value for value in samples.cadence)
    parsed = activity_streams_contracts.ParsedSamples(
        offsets_ms=[_millis_since(start, time) for time in samples.time],
        latitude=latitude,
        longitude=longitude,
        elevation=_channel(_smoothed_altitude(samples)),
        heart_rate=_channel(samples.heart_rate),
        power=_channel(samples.power),
        cadence=cadence,
        speed=_channel(streams.speed_samples),
        temperature=_channel(samples.temperature),
    )
    has_values = any(getattr(parsed, name) is not None for name in activity_streams_constants.SAMPLE_CHANNELS)
    return parsed if has_values else None


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


def _timer_time(
    session: activity_file_import_recording.Session, streams: _Streams, elapsed: float, threshold: float
) -> float:
    """Return a session's timed seconds: the device's, else the sum of its laps' timers, else the moving time.

    Args:
        session: The session.
        streams: The session's streams.
        elapsed: The session's elapsed seconds.
        threshold: The pause threshold in seconds.

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
    moving = activities_computation.moving_time(
        [time.timestamp() for time in session.samples.time],
        streams.sample_speed,
        threshold,
        min_speed=_moving_speed_minimum(session),
    )
    return moving if moving > 0 else elapsed


def _moving_speed_minimum(session: activity_file_import_recording.Session) -> float:
    """Return the slowest speed that is moving in a session's sport.

    Args:
        session: The session.

    Returns:
        The speed in m/s: lower on water, where swimmers and paddlers go slower than on land.
    """
    if activity_file_import_cleaning.is_water_sport(session.sport):
        return activities_computation.MOVING_SPEED_MINIMUM_ON_WATER
    return activities_computation.MOVING_SPEED_MINIMUM


def _distance(
    session: activity_file_import_recording.Session, streams: _Streams, timer: float, threshold: float
) -> float:
    """Return a session's distance in metres.

    Args:
        session: The session.
        streams: The session's streams.
        timer: The session's timed seconds.
        threshold: The pause threshold in seconds.

    Returns:
        The device's distance, else the last distance sample, else the sum of the laps' distances, else the geodesic
        length of the moving steps of the position runs, else the average speed times the timer; ``0.0`` when none
        gives one.
    """
    if session.summary.distance:
        return session.summary.distance
    recorded = [value for value in session.samples.distance if value is not None]
    if recorded and recorded[-1]:
        return recorded[-1]
    if lap_distance := sum(lap.total_distance or 0.0 for lap in session.laps):
        return lap_distance
    samples = session.samples
    walked = activities_computation.moving_distance(
        [time.timestamp() for time in samples.time],
        samples.lat,
        samples.lon,
        streams.sample_speed,
        threshold,
        _breaks(session),
        min_speed=_moving_speed_minimum(session),
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


def _sampled_mean(times: Sequence[datetime], values: Sequence[float | None], threshold: float) -> float | None:
    """Average samples by the time each holds until the next, a pause weighing no more than ``threshold``.

    Args:
        times: The samples' times.
        values: The samples' values, ``None`` where the channel has none.
        threshold: The pause threshold in seconds.

    Returns:
        The time-weighted mean; ``None`` when no sample has a value.
    """
    return activities_computation.time_weighted_mean([time.timestamp() for time in times], values, threshold)


def _sampled_normalized_power(
    times: Sequence[datetime], values: Sequence[float | None], threshold: float
) -> float | None:
    """Compute the normalized power of samples, a pause being left out beyond ``threshold``.

    Args:
        times: The samples' times.
        values: The samples' power, ``None`` where the channel has none.
        threshold: The pause threshold in seconds.

    Returns:
        The normalized power; ``None`` when fewer than 30 seconds of power exist.
    """
    return activities_computation.normalized_power([time.timestamp() for time in times], values, threshold)


def _present_max(values: Iterable[float | None]) -> float | None:
    """Return the largest value that exists.

    Args:
        values: The samples' values, ``None`` where the channel has none.

    Returns:
        The largest value; ``None`` when none exists.
    """
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _heart_rate(session: activity_file_import_recording.Session, threshold: float) -> tuple[int | None, int | None]:
    """Return a session's average and maximum heart rate.

    Args:
        session: The session.
        threshold: The pause threshold in seconds.

    Returns:
        The device's values, with a missing or zero one computed from the samples (a zero is a dropout and is already
        left out of them).
    """
    samples = session.samples
    # A device's 0 is a dropout like a sample's.
    avg, peak = session.summary.avg_heart_rate or None, session.summary.max_heart_rate or None
    if avg is None:
        sampled_avg = _sampled_mean(samples.time, samples.heart_rate, threshold)
        avg = round(sampled_avg) if sampled_avg else None
    if peak is None:
        sampled_max = _present_max(samples.heart_rate)
        peak = round(sampled_max) if sampled_max else None
    return avg, peak


def _power(
    session: activity_file_import_recording.Session, threshold: float
) -> tuple[int | None, int | None, int | None]:
    """Return a session's average, maximum and normalized power.

    Args:
        session: The session.
        threshold: The pause threshold in seconds.

    Returns:
        The device's values, with a missing one computed from the samples; a zero reading counts in the average.
    """
    samples = session.samples
    avg: float | None = session.summary.avg_power
    peak: float | None = session.summary.max_power
    normalized: float | None = session.summary.normalized_power
    if avg is None:
        avg = _sampled_mean(samples.time, samples.power, threshold)
    if peak is None:
        peak = _present_max(samples.power)
    if normalized is None:
        normalized = _sampled_normalized_power(samples.time, samples.power, threshold)
    return (
        round(avg) if avg else None,
        round(peak) if peak else None,
        round(normalized) if normalized else None,
    )


def _cadence_stat(
    summary_value: float | None, fraction: float | None, sampled: float | None, running: bool
) -> int | None:
    """Return one cadence statistic in the unit the activity stores.

    Args:
        summary_value: The device's whole-number value, or ``None``.
        fraction: The device's fractional part.
        sampled: The value computed from the samples, ``None`` when there are none.
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


def _moving_cadence(times: Sequence[datetime], values: Sequence[float | None], threshold: float) -> float | None:
    """Average cadence samples, leaving out the zeros of a rider or runner who was not pedalling or stepping.

    Args:
        times: The samples' times.
        values: The samples' cadence, ``None`` where there is none.
        threshold: The pause threshold in seconds.

    Returns:
        The time-weighted mean of the non-zero samples; ``None`` when there are none.
    """
    return _sampled_mean(times, [value if value else None for value in values], threshold)


def _cadence(
    session: activity_file_import_recording.Session, running: bool, threshold: float
) -> tuple[int | None, int | None]:
    """Return a session's average and maximum cadence.

    Args:
        session: The session, its samples in the device's native cadence unit.
        running: Whether the activity is a running type.
        threshold: The pause threshold in seconds.

    Returns:
        The device's values, with a missing or zero one computed from the samples; steps per minute for running.
    """
    summary, samples = session.summary, session.samples
    return (
        _cadence_stat(
            summary.avg_cadence,
            summary.avg_fractional_cadence,
            _moving_cadence(samples.time, samples.cadence, threshold),
            running,
        ),
        _cadence_stat(summary.max_cadence, summary.max_fractional_cadence, _present_max(samples.cadence), running),
    )


def _elevation(session: activity_file_import_recording.Session, streams: _Streams) -> tuple[int | None, int | None]:
    """Return a session's elevation gain and loss in metres.

    Args:
        session: The session.
        streams: The session's streams.

    Returns:
        The device's values, with a missing one computed from the altitude samples: smoothed over time, then counted
        with a hysteresis.
    """
    gain, loss = session.summary.total_ascent, session.summary.total_descent
    if (gain is None or loss is None) and streams.elevation:
        steps = activity_file_import_parser_utils.elevation_step_waypoints(streams.elevation)
        # A computed 0 m on a flat ride is a real value, not missing data.
        if gain is None:
            gain = round(sum(step["gain"] for step in steps))
        if loss is None:
            loss = round(sum(step["loss"] for step in steps))
    return gain, loss


def _max_speed(
    samples: activity_file_import_recording.Samples, speeds: Sequence[float | None], threshold: float
) -> float | None:
    """Return the best 5 s window mean of measured speeds, over the samples' own times.

    A sample with neither a position nor a speed (its fix dropped by cleaning, or a sensor-only row) is left out, so
    the step across it keeps its full time; a sample with a position but no speed starts a new run, as a placeholder.

    Args:
        samples: The samples.
        speeds: The measured speed at each sample, ``None`` where it has none.
        threshold: The pause threshold in seconds.

    Returns:
        The maximum speed in m/s; ``None`` when there is no measured speed.
    """
    rows = [
        row
        for row, speed in enumerate(speeds)
        if speed is not None or (samples.lat[row] is not None and samples.lon[row] is not None)
    ]
    return activities_computation.rolling_max_speed(
        [samples.time[row].timestamp() for row in rows], [speeds[row] for row in rows], threshold
    )


def _speeds(
    session: activity_file_import_recording.Session,
    streams: _Streams,
    distance: float,
    pace: float | None,
    threshold: float,
) -> tuple[float | None, float | None]:
    """Return a session's average and maximum speed in metres per second.

    Args:
        session: The session.
        streams: The session's streams.
        distance: The session's distance in metres.
        pace: The session's pace in seconds per metre.
        threshold: The pause threshold in seconds.

    Returns:
        The device's values; otherwise the average is the inverse of the pace and the maximum is the best 5 s window
        mean of the measured speed samples. Both are ``None`` without a distance.
    """
    if not distance:
        # A device writes an average speed of 0 for a session that covers no distance (strength, HIIT).
        return None, None
    avg, peak = session.summary.avg_speed, session.summary.max_speed
    if avg is None and pace:
        avg = 1 / pace
    if peak is None:
        # Over the samples' own times, as the laps do: the stream's stamps drop the sub-second part.
        peak = _max_speed(session.samples, streams.step_speed, threshold) or None
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
        avg_hr: Average heart rate, time-weighted.
        max_hr: Maximum heart rate.
        avg_cad: Average cadence as stored (steps per minute for running).
        max_cad: Maximum cadence as stored.
        avg_power: Average power.
        max_power: Maximum power.
        normalized_power: Normalized power.
        max_speed: Highest 5 s window mean of the device speed.
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


def _sampled_lap(window: activity_file_import_recording.Samples, running: bool, threshold: float) -> _LapSamples:
    """Compute a lap's statistics from the samples inside it.

    Args:
        window: The samples inside the lap.
        running: Whether the activity is a running type.
        threshold: The pause threshold in seconds.

    Returns:
        The statistics; ``None`` where the lap has no samples of the channel or the value is zero.
    """
    avg_hr = _sampled_mean(window.time, window.heart_rate, threshold)
    max_hr = _present_max(window.heart_rate)
    avg_cad = _moving_cadence(window.time, window.cadence, threshold)
    max_cad = _present_max(window.cadence)
    avg_power = _sampled_mean(window.time, window.power, threshold)
    max_power = _present_max(window.power)
    normalized_power = _sampled_normalized_power(window.time, window.power, threshold)
    max_speed = _max_speed(window, window.speed, threshold)
    positions = [(lat, lon) for lat, lon in zip(window.lat, window.lon, strict=True) if lat is not None]
    return _LapSamples(
        avg_hr=round(avg_hr) if avg_hr else None,
        max_hr=round(max_hr) if max_hr else None,
        avg_cad=_cadence_stat(None, None, avg_cad, running),
        max_cad=_cadence_stat(None, None, max_cad, running),
        avg_power=round(avg_power) if avg_power else None,
        max_power=round(max_power) if max_power else None,
        normalized_power=round(normalized_power) if normalized_power else None,
        max_speed=max_speed,
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
    threshold: float,
) -> dict[str, object]:
    """Map a device lap to the row a stored lap has.

    Args:
        lap: The lap.
        start: The lap's start.
        elapsed: The lap's elapsed seconds.
        session: The session the lap belongs to.
        running: Whether the activity is a running type.
        last: Whether it is the session's last lap.
        threshold: The session's pause threshold in seconds.

    Returns:
        The lap row; a statistic the device left out is computed from the samples inside the lap, and running cadence
        is stored as steps per minute with the fractional columns cleared.
    """
    # A sample on the instant one lap ends and the next starts belongs to the later lap; the last lap keeps its end.
    end = start + timedelta(seconds=elapsed, microseconds=1 if last else 0)
    window = activity_file_import_recording.samples_between(session.samples, start, end)
    sampled = _sampled_lap(window, running, threshold)
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

    Some exporters omit them from lap messages. They are summed from the per-sample gain and loss of the whole
    altitude stream, so the laps partition the activity's own gain and loss; a value the device reported, even a
    genuine 0, is never replaced.

    Args:
        laps: The lap rows; updated in place.
        elevation: The session's altitude waypoints.
    """
    missing = [lap for lap in laps if lap["total_ascent"] is None or lap["total_descent"] is None]
    if not missing or not elevation:
        return
    steps = activity_file_import_parser_utils.elevation_step_waypoints(elevation)
    for lap in missing:
        start = lap["start_time"]
        elapsed = lap["total_elapsed_time"]
        if not isinstance(start, datetime) or not isinstance(elapsed, int | float):
            continue
        summed = activity_file_import_parser_utils.sum_lap_elevation(
            steps,
            core_timezone.format_utc(start),
            core_timezone.format_utc(start + timedelta(seconds=elapsed)),
        )
        if summed is None:
            continue
        gain, loss = summed
        if lap["total_ascent"] is None:
            lap["total_ascent"] = round(gain)
        if lap["total_descent"] is None:
            lap["total_descent"] = round(loss)


def _auto_laps(
    session: activity_file_import_recording.Session,
    streams: _Streams,
    running: bool,
    lap_distance_km: float,
    threshold: float,
) -> list[Mapping[str, object]]:
    """Build laps of ``lap_distance_km`` over a session's whole moving distance, with no restart at a pause.

    The cumulative distance is the one the activity has, the geodesic length of the moving steps, so the laps add up to
    it and GPS jitter at a stop makes none. A lap closes at the first sample where the distance reaches the next
    multiple of the lap distance; the step ending there belongs wholly to the lap it closes. The first lap starts at
    the first sample and each later one at the closing sample of the one before, and a lap holds the samples after its
    start up to its closing sample, so every sample, step and second of moving time falls in exactly one lap. The
    last lap holds what remains.

    Args:
        session: The session.
        streams: The session's streams.
        running: Whether the activity is a running type.
        lap_distance_km: The distance of a lap.
        threshold: The session's pause threshold in seconds.

    Returns:
        The lap rows in time order; none when the session has no moving distance.
    """
    samples = session.samples
    times = [time.timestamp() for time in samples.time]
    minimum = _moving_speed_minimum(session)
    distances = activities_computation.moving_step_distances(
        times, samples.lat, samples.lon, streams.sample_speed, threshold, _breaks(session), min_speed=minimum
    )
    closes = activities_computation.lap_closes(distances, lap_distance_km * 1000)
    if not closes:
        return []
    timers = activities_computation.moving_durations(times, streams.sample_speed, threshold, min_speed=minimum)
    measured = dataclasses.replace(samples, speed=tuple(streams.step_speed))
    steps = activity_file_import_parser_utils.elevation_step_waypoints(streams.elevation)
    laps: list[Mapping[str, object]] = []
    start = samples.time[0]
    first = 0
    start_position: tuple[float | None, float | None] | None = None
    for close in closes:
        end = samples.time[close]
        window = measured.rows(first, close + 1)
        sampled = _sampled_lap(window, running, threshold)
        distance = sum(distances[first : close + 1])
        timer = sum(timers[first : close + 1])
        avg_speed = distance / timer if timer else None
        elevation = activity_file_import_parser_utils.sum_lap_elevation(
            steps, core_timezone.format_utc(start), core_timezone.format_utc(end)
        )
        start_position = start_position or sampled.start
        laps.append(
            {
                "start_time": core_timezone.format_utc(start),
                "start_position_lat": start_position[0],
                "start_position_long": start_position[1],
                "end_position_lat": sampled.end[0],
                "end_position_long": sampled.end[1],
                "total_elapsed_time": (end - start).total_seconds(),
                "total_timer_time": timer,
                "total_distance": distance,
                "avg_heart_rate": sampled.avg_hr,
                "max_heart_rate": sampled.max_hr,
                "avg_cadence": sampled.avg_cad,
                "max_cadence": sampled.max_cad,
                "avg_power": sampled.avg_power,
                "max_power": sampled.max_power,
                # A flat lap has a genuine 0 m ascent and descent, distinct from missing data.
                "total_ascent": None if elevation is None else round(elevation[0]),
                "total_descent": None if elevation is None else round(elevation[1]),
                "normalized_power": sampled.normalized_power,
                "enhanced_avg_pace": 1 / avg_speed if avg_speed else None,
                "enhanced_avg_speed": avg_speed,
                "enhanced_max_pace": 1 / sampled.max_speed if sampled.max_speed else None,
                "enhanced_max_speed": sampled.max_speed,
            }
        )
        start = end
        first = close + 1
        start_position = sampled.end if sampled.end != (None, None) else None
    return laps


def _laps(
    session: activity_file_import_recording.Session,
    streams: _Streams,
    running: bool,
    lap_distance_km: float,
    threshold: float,
) -> list[Mapping[str, object]]:
    """Build a session's laps: the device's when it recorded any, else one per ``lap_distance_km`` of moving distance.

    Args:
        session: The session.
        streams: The session's streams.
        running: Whether the activity is a running type.
        lap_distance_km: Distance after which a generated lap closes.
        threshold: The session's pause threshold in seconds, for averaging a device lap's samples.

    Returns:
        The lap rows in time order.
    """
    if session.laps:
        rows = [
            _device_lap(lap, *_lap_window(session, i), session, running, i == len(session.laps) - 1, threshold)
            for i, lap in enumerate(session.laps)
        ]
        _fill_lap_elevation(rows, streams.elevation)
        return list(rows)
    return _auto_laps(session, streams, running, lap_distance_km, threshold)


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
    threshold = activities_computation.pause_threshold_seconds(list(session.samples.time))
    timer = _timer_time(session, streams, elapsed, threshold)
    distance = _distance(session, streams, timer, threshold)
    active_time = _active_time(session, distance, timer)
    pace = activities_computation.calculate_pace_from_duration(distance, active_time) or None
    avg_speed, max_speed = _speeds(session, streams, distance, pace, threshold)
    avg_hr, max_hr = _heart_rate(session, threshold)
    avg_power, max_power, normalized_power = _power(session, threshold)
    avg_cadence, max_cadence = _cadence(session, running, threshold)
    elevation_gain, elevation_loss = _elevation(session, streams)

    cadence = activities_computation.double_cadence_waypoints(streams.cadence) if running else streams.cadence
    laps = _laps(session, streams, running, lap_distance_km, threshold)
    start = core_timezone.to_utc_second(session.start_time)
    start_point = streams.lat_lon[0] if streams.lat_lon else None

    stored_type = activity_constants.ActivityType.from_stored(activity_type)
    activity = activity_contracts.ActivityCore(
        user_id=user_id,
        name=stored_type.label if is_leg else _name(recording, activity_name),
        description=recording.description,
        distance=round(distance) if distance else 0,
        activity_type=stored_type,
        start_time=start,
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
        start_latitude=start_point["lat"] if start_point else None,
        start_longitude=start_point["lon"] if start_point else None,
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
        "samples": _build_samples(session, streams, start, running=running),
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
        The parent payload: the legs' totals and no streams, samples, laps, sets or workout steps.
    """
    activities = [leg["activity"] for leg in legs]
    first, last = activities[0], activities[-1]
    start_point = next((leg for leg in activities if leg.start_latitude is not None), first)
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
        start_latitude=start_point.start_latitude,
        start_longitude=start_point.start_longitude,
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
        "samples": None,
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
