"""Encode a :class:`~modules.activities.activity_file_import.recording.Recording` as a GPX 1.1 file.

Each session is one ``trk`` and each run of recording between pauses one ``trkseg``, so ``gpx_decoder`` reads the
pauses back from the gaps between segments. A trackpoint carries its sensor channels in Garmin's
``TrackPointExtension`` v2 (temperature, heart rate, cadence, speed) and its power in Garmin's ``PowerExtension`` v1,
and every value fits its schema's range. GPX holds positioned points only: a sample without a position is not
written, and GPX has no place for laps, cumulative distance or device totals. The encoder computes nothing.
"""

from typing import IO

import core.exceptions as core_exceptions
import modules.activities.activity_file_import.recording as activity_file_import_recording
import modules.activities.activity_file_import.xml_values as activity_file_import_xml_values

_CREATOR = "Endurain"
_GPX_NS = "http://www.topografix.com/GPX/1/1"
_TPX_NS = "http://www.garmin.com/xmlschemas/TrackPointExtension/v2"
_PWR_NS = "http://www.garmin.com/xmlschemas/PowerExtension/v1"
_SCHEMA_LOCATION = (
    f"{_GPX_NS} http://www.topografix.com/GPX/1/1/gpx.xsd "
    f"{_TPX_NS} https://www8.garmin.com/xmlschemas/TrackPointExtensionv2.xsd "
    f"{_PWR_NS} https://www8.garmin.com/xmlschemas/PowerExtensionv1.xsd"
)


def _extensions(samples: activity_file_import_recording.Samples, row: int) -> str:
    """Write a trackpoint's ``extensions``.

    Args:
        samples: The session's samples.
        row: The sample's row.

    Returns:
        The ``extensions`` element, or an empty string when the sample carries no sensor channel.
    """
    number = activity_file_import_xml_values.xml_number
    channels: list[str] = []
    temperature = samples.temperature[row]
    if temperature is not None:
        channels.append(f"<gpxtpx:atemp>{number(temperature)}</gpxtpx:atemp>")
    if (heart_rate := activity_file_import_xml_values.xml_heart_rate(samples.heart_rate[row])) is not None:
        channels.append(f"<gpxtpx:hr>{heart_rate}</gpxtpx:hr>")
    if (cadence := activity_file_import_xml_values.xml_cadence(samples.cadence[row])) is not None:
        channels.append(f"<gpxtpx:cad>{cadence}</gpxtpx:cad>")
    speed = samples.speed[row]
    if speed is not None:
        channels.append(f"<gpxtpx:speed>{number(speed)}</gpxtpx:speed>")
    parts: list[str] = []
    if channels:
        parts.append(f"<gpxtpx:TrackPointExtension>{''.join(channels)}</gpxtpx:TrackPointExtension>")
    if (power := activity_file_import_xml_values.xml_unsigned_short(samples.power[row])) is not None:
        parts.append(f"<gpxpx:PowerInWatts>{power}</gpxpx:PowerInWatts>")
    return f"<extensions>{''.join(parts)}</extensions>" if parts else ""


type _Point = tuple[int, float, float]
"""A positioned sample: its row, latitude and longitude."""


def _trackpoint(samples: activity_file_import_recording.Samples, point: _Point) -> str:
    """Write one positioned sample as a ``trkpt``.

    Args:
        samples: The session's samples.
        point: The sample's row and position.

    Returns:
        The ``trkpt`` element.
    """
    number = activity_file_import_xml_values.xml_number
    row, lat, lon = point
    parts = [f'<trkpt lat="{number(lat)}" lon="{number(lon)}">']
    altitude = samples.altitude[row]
    if altitude is not None:
        parts.append(f"<ele>{number(altitude)}</ele>")
    parts.append(f"<time>{activity_file_import_xml_values.xml_time(samples.time[row])}</time>")
    parts.append(_extensions(samples, row))
    parts.append("</trkpt>")
    return "".join(parts)


def _points(samples: activity_file_import_recording.Samples) -> list[_Point]:
    """Return the samples that carry a position.

    Args:
        samples: The session's samples.

    Returns:
        Each positioned sample's row and position, in time order.
    """
    return [
        (row, lat, lon)
        for row, (lat, lon) in enumerate(zip(samples.lat, samples.lon, strict=True))
        if lat is not None and lon is not None
    ]


def _track_header(recording: activity_file_import_recording.Recording, sport: str | None) -> str:
    """Write a ``trk``'s name, description and type.

    Args:
        recording: The recording, for its name and description.
        sport: The session's sport.

    Returns:
        The elements, in the order GPX 1.1 requires.
    """
    text = activity_file_import_xml_values.xml_text
    parts: list[str] = []
    if recording.name:
        parts.append(f"<name>{text(recording.name)}</name>")
    if recording.description:
        parts.append(f"<desc>{text(recording.description)}</desc>")
    if sport:
        parts.append(f"<type>{text(sport)}</type>")
    return "".join(parts)


def encode_gpx(recording: activity_file_import_recording.Recording, target: IO[bytes]) -> None:
    """Write a recording as a GPX 1.1 file, one track per session that has a position.

    Args:
        recording: The recording.
        target: The binary stream the file is written to, a trackpoint at a time.

    Raises:
        InvalidInputError: When no sample of the recording has a position, since a GPX track holds positioned points
            only.
    """
    tracks = [(session, points) for session in recording.sessions if (points := _points(session.samples))]
    if not tracks:
        raise core_exceptions.InvalidInputError("The recording has no positions to write as GPX")

    def write(text: str) -> None:
        target.write(text.encode("utf-8"))

    first_session, first_points = tracks[0]
    first_time = first_session.samples.time[first_points[0][0]]
    write(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<gpx version="1.1" creator="{_CREATOR}" xmlns="{_GPX_NS}" xmlns:gpxtpx="{_TPX_NS}" xmlns:gpxpx="{_PWR_NS}" '
        f'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="{_SCHEMA_LOCATION}">\n'
        f"<metadata><time>{activity_file_import_xml_values.xml_time(first_time)}</time></metadata>\n"
    )
    for session, points in tracks:
        write(f"<trk>{_track_header(recording, session.sport)}\n")
        times = [session.samples.time[row] for row, _, _ in points]
        for run in activity_file_import_recording.split_at_pauses(times, session.pauses):
            write("<trkseg>\n")
            for index in run:
                write(_trackpoint(session.samples, points[index]) + "\n")
            write("</trkseg>\n")
        write("</trk>\n")
    write("</gpx>\n")
