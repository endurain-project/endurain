"""Encode a :class:`~modules.activities.activity_file_import.recording.Recording` as a TCX v2 file.

Each session is one ``Activity`` and each device lap one ``Lap`` holding the samples from its start to the next lap's;
a session with no laps is written as one lap from its device totals. Inside a lap, each run of recording between
pauses is one ``Track``, so ``tcx_decoder`` reads the pauses back from the gaps between a lap's tracks. Speed, power
and running cadence go in Garmin's ``ActivityExtension`` v2, as Garmin Connect writes them. Elements follow the
schema's order, and the schema's required lap totals are written as ``0`` when the recording has no value. TCX has no
place for temperature, the activity name or lengths, and names only running and biking as sports. The encoder
computes nothing beyond a lap-less session's timer: its span less its pauses.
"""

import bisect
from collections.abc import Iterator
from datetime import timedelta
from typing import IO, Literal

import modules.activities.activity.constants as activity_constants
import modules.activities.activity_file_import.recording as activity_file_import_recording
import modules.activities.activity_file_import.xml_values as activity_file_import_xml_values

_TCX_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
_EXT_NS = "http://www.garmin.com/xmlschemas/ActivityExtension/v2"
_SCHEMA_LOCATION = (
    f"{_TCX_NS} https://www8.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd "
    f"{_EXT_NS} https://www8.garmin.com/xmlschemas/ActivityExtensionv2.xsd"
)

#: A lap's ``TriggerMethod`` for each lap trigger a decoder names; any other trigger is ``Manual``.
_TRIGGER_METHODS = {
    "distance": "Distance",
    "time": "Time",
    "heart_rate": "HeartRate",
    "heartrate": "HeartRate",
    "location": "Location",
    "position_start": "Location",
    "position_lap": "Location",
    "position_waypoint": "Location",
    "position_marked": "Location",
}

#: Lap intensities written as ``Resting``; any other is ``Active``.
_RESTING = frozenset({"rest", "resting"})

type _Sport = Literal["Running", "Biking", "Other"]


def _sport(sport: str | None) -> _Sport:
    """Name a session's sport as TCX does.

    Args:
        sport: The session's sport.

    Returns:
        ``Running`` or ``Biking`` for an activity type of those sports, ``Other`` for any other.
    """
    activity_type = activity_constants.define_activity_type(sport) if sport else None
    if activity_type in activity_constants.ACTIVITY_TYPES_BY_SPORT["run"]:
        return "Running"
    if activity_type in activity_constants.ACTIVITY_TYPES_BY_SPORT["bike"]:
        return "Biking"
    return "Other"


def _session_lap(session: activity_file_import_recording.Session) -> activity_file_import_recording.Lap:
    """Make the one lap a session with no laps is written as, from its device totals.

    Args:
        session: The session.

    Returns:
        A lap from the session's start with its totals; its timer is the device's, else the span from the start to
        the last sample less the pauses.
    """
    summary = session.summary
    samples = session.samples
    timer = summary.total_timer_time
    if timer is None and len(samples):
        paused = sum((pause.end - pause.start for pause in session.pauses), timedelta())
        timer = max((samples.time[-1] - session.start_time - paused).total_seconds(), 0.0)
    distance = summary.distance
    if distance is None:
        recorded = [value for value in samples.distance if value is not None]
        distance = recorded[-1] if recorded else None
    return activity_file_import_recording.Lap(
        start_time=session.start_time,
        total_timer_time=timer,
        total_elapsed_time=summary.total_elapsed_time,
        total_distance=distance,
        total_calories=summary.calories,
        total_cycles=summary.total_cycles,
        avg_heart_rate=summary.avg_heart_rate,
        max_heart_rate=summary.max_heart_rate,
        avg_cadence=summary.avg_cadence,
        max_cadence=summary.max_cadence,
        avg_power=summary.avg_power,
        max_power=summary.max_power,
        avg_speed=summary.avg_speed,
        max_speed=summary.max_speed,
    )


def _trackpoint(samples: activity_file_import_recording.Samples, row: int, running: bool) -> str:
    """Write one sample as a ``Trackpoint``.

    Args:
        samples: The session's samples.
        row: The sample's row.
        running: Whether the session is a run, whose cadence goes in the ``RunCadence`` extension.

    Returns:
        The ``Trackpoint`` element.
    """
    number = activity_file_import_xml_values.xml_number
    parts = [f"<Trackpoint><Time>{activity_file_import_xml_values.xml_time(samples.time[row])}</Time>"]
    lat, lon = samples.lat[row], samples.lon[row]
    if lat is not None and lon is not None:
        parts.append(
            f"<Position><LatitudeDegrees>{number(lat)}</LatitudeDegrees>"
            f"<LongitudeDegrees>{number(lon)}</LongitudeDegrees></Position>"
        )
    if (altitude := samples.altitude[row]) is not None:
        parts.append(f"<AltitudeMeters>{number(altitude)}</AltitudeMeters>")
    if (distance := samples.distance[row]) is not None:
        parts.append(f"<DistanceMeters>{number(distance)}</DistanceMeters>")
    if (heart_rate := activity_file_import_xml_values.xml_heart_rate(samples.heart_rate[row])) is not None:
        parts.append(f"<HeartRateBpm><Value>{heart_rate}</Value></HeartRateBpm>")
    cadence = activity_file_import_xml_values.xml_cadence(samples.cadence[row])
    if cadence is not None and not running:
        parts.append(f"<Cadence>{cadence}</Cadence>")
    extension: list[str] = []
    if (speed := samples.speed[row]) is not None:
        extension.append(f"<ns3:Speed>{number(speed)}</ns3:Speed>")
    if cadence is not None and running:
        extension.append(f"<ns3:RunCadence>{cadence}</ns3:RunCadence>")
    if (power := activity_file_import_xml_values.xml_unsigned_short(samples.power[row])) is not None:
        extension.append(f"<ns3:Watts>{power}</ns3:Watts>")
    if extension:
        parts.append(f"<Extensions><ns3:TPX>{''.join(extension)}</ns3:TPX></Extensions>")
    parts.append("</Trackpoint>")
    return "".join(parts)


def _lap_totals(lap: activity_file_import_recording.Lap, running: bool) -> str:
    """Write a lap's totals up to its ``TriggerMethod``, in the schema's order.

    Args:
        lap: The lap.
        running: Whether the session is a run, whose average cadence goes in the lap extension.

    Returns:
        The elements before the lap's tracks.
    """
    number = activity_file_import_xml_values.xml_number
    timer = lap.total_timer_time if lap.total_timer_time is not None else lap.total_elapsed_time
    parts = [
        f"<TotalTimeSeconds>{number(timer or 0.0)}</TotalTimeSeconds>",
        f"<DistanceMeters>{number(lap.total_distance or 0.0)}</DistanceMeters>",
    ]
    if lap.max_speed is not None:
        parts.append(f"<MaximumSpeed>{number(lap.max_speed)}</MaximumSpeed>")
    parts.append(f"<Calories>{activity_file_import_xml_values.xml_unsigned_short(lap.total_calories) or 0}</Calories>")
    if (avg_heart_rate := activity_file_import_xml_values.xml_heart_rate(lap.avg_heart_rate)) is not None:
        parts.append(f"<AverageHeartRateBpm><Value>{avg_heart_rate}</Value></AverageHeartRateBpm>")
    if (max_heart_rate := activity_file_import_xml_values.xml_heart_rate(lap.max_heart_rate)) is not None:
        parts.append(f"<MaximumHeartRateBpm><Value>{max_heart_rate}</Value></MaximumHeartRateBpm>")
    parts.append(f"<Intensity>{'Resting' if lap.intensity in _RESTING else 'Active'}</Intensity>")
    avg_cadence = activity_file_import_xml_values.xml_cadence(lap.avg_cadence)
    if avg_cadence is not None and not running:
        parts.append(f"<Cadence>{avg_cadence}</Cadence>")
    parts.append(f"<TriggerMethod>{_TRIGGER_METHODS.get(lap.lap_trigger or '', 'Manual')}</TriggerMethod>")
    return "".join(parts)


def _lap_extension(lap: activity_file_import_recording.Lap, running: bool) -> str:
    """Write a lap's ``Extensions``, in the schema's order.

    Args:
        lap: The lap.
        running: Whether the session is a run, whose cadence and steps the extension carries.

    Returns:
        The ``Extensions`` element, or an empty string when the lap has nothing for it.
    """
    parts: list[str] = []
    if lap.avg_speed is not None:
        parts.append(f"<ns3:AvgSpeed>{activity_file_import_xml_values.xml_number(lap.avg_speed)}</ns3:AvgSpeed>")
    max_cadence = activity_file_import_xml_values.xml_cadence(lap.max_cadence)
    if max_cadence is not None and not running:
        parts.append(f"<ns3:MaxBikeCadence>{max_cadence}</ns3:MaxBikeCadence>")
    if running:
        if (avg_cadence := activity_file_import_xml_values.xml_cadence(lap.avg_cadence)) is not None:
            parts.append(f"<ns3:AvgRunCadence>{avg_cadence}</ns3:AvgRunCadence>")
        if max_cadence is not None:
            parts.append(f"<ns3:MaxRunCadence>{max_cadence}</ns3:MaxRunCadence>")
        if (steps := activity_file_import_xml_values.xml_unsigned_short(lap.total_cycles)) is not None:
            parts.append(f"<ns3:Steps>{steps}</ns3:Steps>")
    if (avg_power := activity_file_import_xml_values.xml_unsigned_short(lap.avg_power)) is not None:
        parts.append(f"<ns3:AvgWatts>{avg_power}</ns3:AvgWatts>")
    if (max_power := activity_file_import_xml_values.xml_unsigned_short(lap.max_power)) is not None:
        parts.append(f"<ns3:MaxWatts>{max_power}</ns3:MaxWatts>")
    return f"<Extensions><ns3:LX>{''.join(parts)}</ns3:LX></Extensions>" if parts else ""


def _lap_rows(
    session: activity_file_import_recording.Session, laps: tuple[activity_file_import_recording.Lap, ...]
) -> list[list[int]]:
    """Group a session's sample rows by the lap they fall in.

    Args:
        session: The session.
        laps: The laps written for it, in time order.

    Returns:
        The rows of each lap: from its start to the next lap's start; samples before the first lap go in the first.
    """
    starts = [lap.start_time for lap in laps]
    rows: list[list[int]] = [[] for _ in laps]
    for row, time in enumerate(session.samples.time):
        rows[max(bisect.bisect_right(starts, time) - 1, 0)].append(row)
    return rows


def _activity(
    recording: activity_file_import_recording.Recording, session: activity_file_import_recording.Session
) -> Iterator[str]:
    """Write one session as an ``Activity``, a lap at a time.

    Args:
        recording: The recording, for its description.
        session: The session.

    Yields:
        The element's text in pieces.
    """
    sport = _sport(session.sport)
    running = sport == "Running"
    samples = session.samples
    laps = session.laps or (_session_lap(session),)
    yield f'<Activity Sport="{sport}"><Id>{activity_file_import_xml_values.xml_time(session.start_time)}</Id>\n'
    for lap, rows in zip(laps, _lap_rows(session, laps), strict=True):
        start = activity_file_import_xml_values.xml_time(lap.start_time)
        yield f'<Lap StartTime="{start}">{_lap_totals(lap, running)}\n'
        times = [samples.time[row] for row in rows]
        for run in activity_file_import_recording.split_at_pauses(times, session.pauses):
            yield "<Track>\n"
            for index in run:
                yield _trackpoint(samples, rows[index], running) + "\n"
            yield "</Track>\n"
        yield f"{_lap_extension(lap, running)}</Lap>\n"
    if recording.description:
        yield f"<Notes>{activity_file_import_xml_values.xml_text(recording.description)}</Notes>\n"
    yield "</Activity>\n"


def encode_tcx(recording: activity_file_import_recording.Recording, target: IO[bytes]) -> None:
    """Write a recording as a TCX v2 file, one activity per session.

    Args:
        recording: The recording.
        target: The binary stream the file is written to, a trackpoint at a time.
    """
    target.write(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<TrainingCenterDatabase xmlns="{_TCX_NS}" xmlns:ns3="{_EXT_NS}" '
        f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="{_SCHEMA_LOCATION}">\n'
        "<Activities>\n".encode()
    )
    for session in recording.sessions:
        for piece in _activity(recording, session):
            target.write(piece.encode("utf-8"))
    target.write(b"</Activities>\n</TrainingCenterDatabase>\n")
