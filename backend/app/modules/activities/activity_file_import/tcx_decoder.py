"""Decode a TCX file into a :class:`~modules.activities.activity_file_import.recording.Recording`.

The decoder streams the file with ``defusedxml`` and matches elements by local name, so any namespace prefix works.
Each ``Activity`` is one session. It keeps what the file says and does no math: a value the file leaves out or writes
as an unusable number is ``None``.
"""

from datetime import datetime
from xml.etree.ElementTree import Element

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, iterparse

import core.exceptions as core_exceptions
import modules.activities.activity_file_import.recording as activity_file_import_recording
import modules.activities.activity_file_import.xml_values as activity_file_import_xml_values

_ROOT = "TrainingCenterDatabase"
_NO_TIME_MESSAGE = "Invalid TCX file - no activity start or end time found"


def _fields(element: Element | None) -> dict[str, Element]:
    """Index an element's direct children by local name, the first of each name.

    Args:
        element: The parent, or ``None``.

    Returns:
        The children by local name; empty for ``None``.
    """
    fields: dict[str, Element] = {}
    if element is None:
        return fields
    for child in element:
        fields.setdefault(activity_file_import_xml_values.local_name(child.tag), child)
    return fields


def _extension(element: Element | None, name: str) -> dict[str, Element]:
    """Index the children of the ``name`` element inside an ``Extensions`` element.

    Args:
        element: The ``Extensions`` element, or ``None``.
        name: The local name of the extension (``TPX`` or ``LX``).

    Returns:
        The extension's children by local name; empty when it is absent.
    """
    if element is None:
        return {}
    for child in element:
        if activity_file_import_xml_values.local_name(child.tag) == name:
            return _fields(child)
    return {}


def _number(element: Element | None) -> float | None:
    """Read an element's text as a finite number.

    Args:
        element: The element, or ``None``.

    Returns:
        The number, or ``None`` when absent, not a number or not finite.
    """
    return None if element is None else activity_file_import_xml_values.finite_number(element.text)


def _integer(element: Element | None) -> int | None:
    """Read an element's text as a whole number.

    Args:
        element: The element, or ``None``.

    Returns:
        The number rounded to a whole number, or ``None`` when it is not a finite number.
    """
    value = _number(element)
    return None if value is None else round(value)


def _lowered(element: Element | None) -> str | None:
    """Read an element's text in lower case.

    Args:
        element: The element, or ``None``.

    Returns:
        The text, or ``None`` when absent or blank.
    """
    if element is None or element.text is None or not element.text.strip():
        return None
    return element.text.strip().lower()


def _position(fields: dict[str, Element]) -> tuple[float | None, float | None]:
    """Read a trackpoint's position.

    Args:
        fields: The trackpoint's children by local name.

    Returns:
        Latitude and longitude, both ``None`` when the position is absent, unparseable or out of range.
    """
    position = _fields(fields.get("Position"))
    lat, lon = position.get("LatitudeDegrees"), position.get("LongitudeDegrees")
    return activity_file_import_xml_values.position(
        None if lat is None else lat.text, None if lon is None else lon.text
    )


def _read_lap(element: Element, samples_have_cadence: bool) -> activity_file_import_recording.Lap | None:
    """Read a ``Lap`` element.

    The schema defines the lap's ``Cadence`` as its average, but Garmin Connect writes the lap's highest cadence
    there. When the lap's own trackpoints carry cadence, the lap's cadence is left to them; ``Cadence`` is read as the
    schema's average only for a lap whose trackpoints carry none.

    Args:
        element: The ``Lap`` element.
        samples_have_cadence: Whether a trackpoint of the lap carries cadence.

    Returns:
        The lap, or ``None`` when its ``StartTime`` is missing or unparseable.
    """
    start = activity_file_import_xml_values.utc_time(element.get("StartTime"))
    if start is None:
        return None
    fields = _fields(element)
    lx = _extension(fields.get("Extensions"), "LX")
    avg_cadence = _integer(lx.get("AvgRunCadence"))
    if avg_cadence is None and not samples_have_cadence:
        avg_cadence = _integer(fields.get("Cadence"))
    max_cadence = _integer(lx.get("MaxRunCadence"))
    if max_cadence is None:
        max_cadence = _integer(lx.get("MaxBikeCadence"))
    return activity_file_import_recording.Lap(
        start_time=start,
        total_timer_time=_number(fields.get("TotalTimeSeconds")),
        total_distance=_number(fields.get("DistanceMeters")),
        max_speed=_number(fields.get("MaximumSpeed")),
        total_calories=_integer(fields.get("Calories")),
        avg_heart_rate=_integer(_fields(fields.get("AverageHeartRateBpm")).get("Value")),
        max_heart_rate=_integer(_fields(fields.get("MaximumHeartRateBpm")).get("Value")),
        intensity=_lowered(fields.get("Intensity")),
        lap_trigger=_lowered(fields.get("TriggerMethod")),
        avg_cadence=avg_cadence,
        max_cadence=max_cadence,
        avg_speed=_number(lx.get("AvgSpeed")),
        avg_power=_integer(lx.get("AvgWatts")),
        max_power=_integer(lx.get("MaxWatts")),
        total_cycles=_integer(lx.get("Steps")),
    )


class _ActivityReader:
    """Collects one ``Activity``: its trackpoints, laps, track boundaries and id time."""

    def __init__(self, sport: str | None, limits: activity_file_import_recording.FileLimits) -> None:
        """Start an empty activity.

        Args:
            sport: The ``Sport`` attribute.
            limits: The file's limits.
        """
        self.sport = sport.strip() if sport and sport.strip() else None
        self.id_time: datetime | None = None
        self._builder = activity_file_import_recording.SamplesBuilder(limits)
        self._laps: list[activity_file_import_recording.Lap] = []
        self._pauses: list[activity_file_import_recording.Pause] = []
        self._track_start: datetime | None = None
        self._track_end: datetime | None = None
        self._previous_end: datetime | None = None
        self._lap_has_cadence = False
        self._lap_has_track = False

    def start_lap(self) -> None:
        """Begin a ``Lap``."""
        self._lap_has_cadence = False
        self._lap_has_track = False

    def start_track(self) -> None:
        """Begin a ``Track``."""
        self._track_start = None
        self._track_end = None

    def end_track(self) -> None:
        """End a ``Track``; a gap since the previous track of the same lap is a pause.

        A lap's first track starts a new lap, not a resumed recording, so the gap before it is no pause.
        """
        start, end = self._track_start, self._track_end
        if start is None or end is None:
            return
        previous = self._previous_end
        if self._lap_has_track and previous is not None and start > previous:
            self._pauses.append(activity_file_import_recording.Pause(start=previous, end=start))
        self._lap_has_track = True
        if previous is None or end > previous:
            self._previous_end = end

    def add_lap(self, element: Element) -> None:
        """Add a ``Lap`` element's summary.

        Args:
            element: The ``Lap`` element.
        """
        lap = _read_lap(element, self._lap_has_cadence)
        if lap is not None:
            self._laps.append(lap)

    def add_trackpoint(self, element: Element) -> None:
        """Add a ``Trackpoint`` element as a sample; one without a parseable time is skipped.

        Args:
            element: The ``Trackpoint`` element.

        Raises:
            InvalidInputError: When the file passes the sample limit.
        """
        fields = _fields(element)
        time = activity_file_import_xml_values.utc_time(fields["Time"].text) if "Time" in fields else None
        if time is None:
            return
        lat, lon = _position(fields)
        tpx = _extension(fields.get("Extensions"), "TPX")
        cadence = activity_file_import_xml_values.non_negative(
            _number(fields["Cadence"]) if "Cadence" in fields else _number(tpx.get("RunCadence"))
        )
        if cadence is not None:
            self._lap_has_cadence = True
        self._builder.append(
            time,
            lat=lat,
            lon=lon,
            altitude=_number(fields.get("AltitudeMeters")),
            distance=_number(fields.get("DistanceMeters")),
            speed=activity_file_import_xml_values.non_negative(_number(tpx.get("Speed"))),
            heart_rate=activity_file_import_xml_values.whole(_number(_fields(fields.get("HeartRateBpm")).get("Value"))),
            cadence=cadence,
            power=activity_file_import_xml_values.whole(_number(tpx.get("Watts"))),
        )
        if self._track_start is None or time < self._track_start:
            self._track_start = time
        if self._track_end is None or time > self._track_end:
            self._track_end = time

    def build(self) -> activity_file_import_recording.Session:
        """Return the activity as a session.

        Returns:
            The session.

        Raises:
            InvalidInputError: When the activity holds no timed trackpoint.
        """
        if len(self._builder) == 0:
            raise core_exceptions.InvalidInputError(_NO_TIME_MESSAGE)
        samples = self._builder.build()
        start = self.id_time
        if start is None:
            start = self._laps[0].start_time if self._laps else samples.time[0]
        calories = [lap.total_calories for lap in self._laps if lap.total_calories is not None]
        return activity_file_import_recording.Session(
            sport=self.sport,
            start_time=start,
            samples=samples,
            pauses=tuple(self._pauses),
            laps=tuple(self._laps),
            summary=activity_file_import_recording.DeviceSummary(calories=sum(calories) if calories else None),
        )


def _text(element: Element) -> str | None:
    """Return an element's text, ``None`` when blank.

    Args:
        element: The element.

    Returns:
        The stripped text, or ``None``.
    """
    return element.text.strip() if element.text and element.text.strip() else None


def decode_tcx(path: str) -> activity_file_import_recording.Recording:
    """Read a TCX file into a recording, one session per ``Activity``.

    Args:
        path: The TCX file.

    Returns:
        The recording.

    Raises:
        InvalidInputError: When the file is not well-formed TCX, holds no usable activity or passes a file limit.
        ProcessingError: When the file cannot be read.
    """
    limits = activity_file_import_recording.FileLimits()
    sessions: list[activity_file_import_recording.Session] = []
    creator: str | None = None
    description: str | None = None
    stack: list[Element] = []
    activity: _ActivityReader | None = None
    try:
        with open(path, "rb") as source:
            for event, element in iterparse(source, events=("start", "end"), forbid_dtd=True):
                name = activity_file_import_xml_values.local_name(element.tag)
                if event == "start":
                    if not stack and name != _ROOT:
                        raise core_exceptions.InvalidInputError("Invalid TCX file - not a TrainingCenterDatabase")
                    stack.append(element)
                    if name == "Activity":
                        limits.count_session()
                        activity = _ActivityReader(element.get("Sport"), limits)
                    elif name == "Lap" and activity is not None:
                        activity.start_lap()
                    elif name == "Track" and activity is not None:
                        activity.start_track()
                    continue
                stack.pop()
                parent = stack[-1] if stack else None
                parent_name = activity_file_import_xml_values.local_name(parent.tag) if parent is not None else ""
                if activity is None:
                    continue
                if name == "Trackpoint":
                    activity.add_trackpoint(element)
                elif name == "Track":
                    activity.end_track()
                elif name == "Lap":
                    activity.add_lap(element)
                elif name == "Id" and parent_name == "Activity":
                    activity.id_time = activity_file_import_xml_values.utc_time(element.text)
                elif name == "Notes" and parent_name == "Activity" and description is None:
                    description = _text(element)
                elif name == "Name" and parent_name == "Creator" and creator is None:
                    creator = _text(element)
                elif name == "Activity":
                    sessions.append(activity.build())
                    activity = None
                if name in {"Trackpoint", "Track", "Lap", "Activity"} and parent is not None:
                    parent.remove(element)
    except (ParseError, DefusedXmlException) as err:
        raise core_exceptions.InvalidInputError("Can't open TCX file") from err
    except OSError as err:
        raise core_exceptions.ProcessingError("Can't open TCX file") from err
    if not sessions:
        raise core_exceptions.InvalidInputError("Invalid TCX file - no activity found")
    return activity_file_import_recording.Recording(
        format="tcx",
        sessions=tuple(sessions),
        description=description,
        creator=creator,
    )
