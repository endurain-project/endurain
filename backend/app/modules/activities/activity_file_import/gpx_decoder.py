"""Decode a GPX file into a :class:`~modules.activities.activity_file_import.recording.Recording`.

The decoder streams the file and keeps what it says: no distance, speed, smoothing or averages are computed. A value
that is not a usable number is ``None`` for that channel only. A file is one session holding every track and segment.
"""

from datetime import datetime
from xml.etree.ElementTree import Element

import defusedxml.ElementTree

import core.exceptions as core_exceptions
import modules.activities.activity_file_import.recording as activity_file_import_recording
import modules.activities.activity_file_import.xml_values as activity_file_import_xml_values

# Inclusive plausible elevation range in metres; values outside it are sentinel or garbage readings.
_ELEVATION_MIN = -9999.99
_ELEVATION_MAX = 9999.99

#: GPX ``<type>`` names ``activity_constants.define_activity_type`` does not resolve, mapped to ones it does.
_SPORT_BY_GPX_TYPE = {"road_biking": "cycling"}

#: Elements dropped from their parent once processed, so a long file does not keep its parsed tree in memory.
_RELEASED = frozenset({"trkpt", "trkseg", "trk", "wpt", "rte"})

_HEART_RATE = frozenset({"hr", "heartrate", "heart_rate"})
_CADENCE = frozenset({"cad", "cadence"})
_POWER = frozenset({"power", "powerinwatts", "watts"})
_TEMPERATURE = frozenset({"atemp", "temp", "temperature"})
_SPEED = frozenset({"speed"})


def _elevation(text: str | None) -> float | None:
    """Read an elevation in metres.

    Args:
        text: The raw text.

    Returns:
        The elevation, or ``None`` when it is unusable or outside the plausible range.
    """
    value = activity_file_import_xml_values.finite_number(text)
    if value is None or not _ELEVATION_MIN <= value <= _ELEVATION_MAX:
        return None
    return value


def _pauses(segments: list[tuple[datetime, datetime]]) -> tuple[activity_file_import_recording.Pause, ...]:
    """Return a pause for each gap between segments.

    Args:
        segments: The first and last time of each timed segment.

    Returns:
        The pauses in time order.
    """
    pauses: list[activity_file_import_recording.Pause] = []
    ordered = sorted(segments)
    ended = ordered[0][1]
    for start, end in ordered[1:]:
        if start > ended:
            pauses.append(activity_file_import_recording.Pause(start=ended, end=start))
        ended = max(ended, end)
    return tuple(pauses)


class _Reader:
    """Reads the elements of one GPX file in document order, collecting its tracks into one sample table."""

    def __init__(self) -> None:
        """Start with nothing read."""
        self.limits = activity_file_import_recording.FileLimits()
        self.builder = activity_file_import_recording.SamplesBuilder(self.limits)
        self.creator: str | None = None
        self.has_track = False
        self.sport: str | None = None
        self.name: str | None = None
        self.description: str | None = None
        self.metadata_name: str | None = None
        self.metadata_description: str | None = None
        self.calories: int | None = None
        self.segments: list[tuple[datetime, datetime]] = []
        self._segment: list[datetime] = []
        self._point: dict[str, str | None] | None = None
        self._stack: list[tuple[str, Element]] = []

    def start(self, elem: Element) -> None:
        """Handle an element that opens.

        Args:
            elem: The element.
        """
        name = activity_file_import_xml_values.local_name(elem.tag).lower()
        if not self._stack:
            if name != "gpx":
                raise core_exceptions.InvalidInputError("Invalid GPX file - the root element is not gpx")
            self.creator = (elem.get("creator") or "").strip() or None
        self._stack.append((name, elem))
        if name == "trk":
            self.has_track = True
        elif name == "trkpt":
            self._point = {"lat": elem.get("lat"), "lon": elem.get("lon")}
        elif name == "trkseg":
            self._segment = []

    def end(self, elem: Element) -> None:
        """Handle an element that closes.

        Args:
            elem: The element.
        """
        name, _ = self._stack.pop()
        parent = self._stack[-1][0] if self._stack else None
        text = elem.text
        if self._point is not None and name != "trkpt":
            self._read_point_element(name, parent, text)
        elif name == "trkpt":
            self._finish_point()
        elif name == "trkseg":
            if self._segment:
                self.segments.append((min(self._segment), max(self._segment)))
        elif parent == "trk" and text and text.strip():
            self._read_track_element(name, text.strip())
        elif name == "calories" and any(entry == "trk" for entry, _ in self._stack):
            self._add_calories(text)
        elif parent == "metadata" and text and text.strip():
            if name == "name" and self.metadata_name is None:
                self.metadata_name = text.strip()
            elif name == "desc" and self.metadata_description is None:
                self.metadata_description = text.strip()
        if name in _RELEASED:
            elem.clear()
            if self._stack:
                self._stack[-1][1].remove(elem)

    def _read_point_element(self, name: str, parent: str | None, text: str | None) -> None:
        """Keep the value of an element inside a trackpoint.

        Args:
            name: The element's lowercase local name.
            parent: The parent's lowercase local name.
            text: The element's text.
        """
        point = self._point
        if point is None:
            return
        if parent == "trkpt" and name in ("ele", "time"):
            point[name] = text
        elif name in _HEART_RATE:
            point["hr"] = text
        elif name in _CADENCE:
            point["cad"] = text
        elif name in _POWER:
            point["power"] = text
        elif name in _TEMPERATURE:
            point["temp"] = text
        elif name in _SPEED:
            point["speed"] = text

    def _read_track_element(self, name: str, text: str) -> None:
        """Keep a track's own name, description or type, the first of each in the file.

        Args:
            name: The element's lowercase local name.
            text: The element's stripped text.
        """
        if name == "name" and self.name is None:
            self.name = text
        elif name == "desc" and self.description is None:
            self.description = text
        elif name == "type" and self.sport is None:
            self.sport = _SPORT_BY_GPX_TYPE.get(text.lower(), text)

    def _add_calories(self, text: str | None) -> None:
        """Add a track's calories extension to the file's total.

        Args:
            text: The element's text.
        """
        value = activity_file_import_xml_values.finite_number(text)
        if value is not None:
            self.calories = (self.calories or 0) + int(value)

    def _finish_point(self) -> None:
        """Append the trackpoint just closed, unless it has no usable time.

        Raises:
            InvalidInputError: When the file passes the sample limit.
        """
        point = self._point
        self._point = None
        if point is None:
            return
        time = activity_file_import_xml_values.utc_time(point.get("time"))
        if time is None:
            return
        lat, lon = activity_file_import_xml_values.position(point.get("lat"), point.get("lon"))
        self.builder.append(
            time,
            lat=lat,
            lon=lon,
            altitude=_elevation(point.get("ele")),
            speed=activity_file_import_xml_values.non_negative(
                activity_file_import_xml_values.finite_number(point.get("speed"))
            ),
            heart_rate=activity_file_import_xml_values.whole(
                activity_file_import_xml_values.finite_number(point.get("hr"))
            ),
            cadence=activity_file_import_xml_values.non_negative(
                activity_file_import_xml_values.finite_number(point.get("cad"))
            ),
            power=activity_file_import_xml_values.whole(
                activity_file_import_xml_values.finite_number(point.get("power"))
            ),
            temperature=activity_file_import_xml_values.finite_number(point.get("temp")),
        )
        self._segment.append(time)


def decode_gpx(path: str) -> activity_file_import_recording.Recording:
    """Decode a GPX file.

    All tracks and segments become one session with its samples in time order, and a gap between two segments becomes
    a pause. A trackpoint without a usable time is skipped.

    Args:
        path: The GPX file.

    Returns:
        The file's recording.

    Raises:
        InvalidInputError: When the file is not well-formed XML or not GPX, holds no track or fewer than two timed
            trackpoints, or passes a file limit.
        ProcessingError: When the file cannot be read.
    """
    reader = _Reader()
    try:
        with open(path, "rb") as gpx_file:
            for event, elem in defusedxml.ElementTree.iterparse(gpx_file, events=("start", "end"), forbid_dtd=True):
                if event == "start":
                    reader.start(elem)
                else:
                    reader.end(elem)
    except core_exceptions.DomainError:
        raise
    except (defusedxml.ElementTree.ParseError, defusedxml.DefusedXmlException, ValueError) as err:
        raise core_exceptions.InvalidInputError("Failed to parse GPX file") from err
    except OSError as err:
        raise core_exceptions.ProcessingError("Failed to read GPX file") from err

    if not reader.has_track:
        raise core_exceptions.InvalidInputError("Invalid GPX file - no tracks found in the GPX file")
    samples = len(reader.builder)
    if samples == 0:
        raise core_exceptions.InvalidInputError("Invalid GPX file - no trackpoints with valid time data found")
    if samples < 2:
        raise core_exceptions.InvalidInputError(
            "Invalid GPX file - no valid segments with at least two timed GPS trackpoints found"
        )

    reader.limits.count_session()
    table = reader.builder.build()
    session = activity_file_import_recording.Session(
        sport=reader.sport,
        start_time=table.time[0],
        samples=table,
        pauses=_pauses(reader.segments),
        summary=activity_file_import_recording.DeviceSummary(calories=reader.calories),
    )
    return activity_file_import_recording.Recording(
        format="gpx",
        sessions=(session,),
        name=reader.name or reader.metadata_name,
        description=reader.description or reader.metadata_description,
        creator=reader.creator,
    )
