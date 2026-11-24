"""Synthetic GPX, TCX and FIT files for edge cases no real device file exists for.

Each builder returns the bytes of one small file and states in its docstring the edge case it pins. ``CASES`` maps
``"<format>/<name>.<format>"`` to its builder; ``test_device_files.py`` snapshots every case like a real device file,
so a parser change shows up as a golden diff. Everything is deterministic: noise comes from a tiny explicit LCG.
"""

import math
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

from tests.activities.activity_file_import import fit_files
from tests.activities.activity_file_import.fit_files import RawField

type Point = dict[str, object]

_START = datetime(2026, 6, 20, 8, 0, 0, tzinfo=UTC)
_LAT = 38.7
_LON = -9.1
_METERS_PER_DEGREE = 111_320.0

_GPX_NS = "http://www.topografix.com/GPX/1/1"
_TPX_NS = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"
_PWR_NS = "http://www.garmin.com/xmlschemas/PowerExtension/v1"
_TCX_NS = "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
_TCX_EXT_NS = "http://www.garmin.com/xmlschemas/ActivityExtension/v2"


def _noise(seed: int) -> Iterator[float]:
    """Yield a deterministic pseudo-random sequence in [-1, 1) from a linear congruential generator."""
    state = seed
    while True:
        state = (state * 1_103_515_245 + 12_345) % 2**31
        yield state / 2**30 - 1.0


def _stamp(moment: datetime, offset_hours: int | None = 0) -> str:
    """Format a UTC instant as ISO 8601: ``Z`` for 0, ``+HH:00`` for another offset, naive for None.

    Milliseconds are written only when the instant has a sub-second part.
    """
    local = moment if offset_hours is None else moment + timedelta(hours=offset_hours)
    text = local.strftime("%Y-%m-%dT%H:%M:%S")
    if local.microsecond:
        text += f".{local.microsecond // 1000:03d}"
    if offset_hours is None:
        return text
    return text + ("Z" if offset_hours == 0 else f"{offset_hours:+03d}:00")


def _track(
    count: int,
    *,
    start: datetime = _START,
    lat: float = _LAT,
    lon: float = _LON,
    speed: float = 3.0,
    heading: float = 90.0,
    step: float = 1.0,
) -> list[Point]:
    """Return ``count`` timed points moving at ``speed`` m/s along ``heading`` degrees, one every ``step`` seconds."""
    points: list[Point] = []
    for index in range(count):
        meters = speed * step * index
        north = meters * math.cos(math.radians(heading))
        east = meters * math.sin(math.radians(heading))
        points.append(
            {
                "lat": round(lat + north / _METERS_PER_DEGREE, 7),
                "lon": round(lon + east / (_METERS_PER_DEGREE * math.cos(math.radians(lat))), 7),
                "time": start + timedelta(seconds=step * index),
            }
        )
    return points


def _decorate(points: list[Point], **fields: Callable[[int], object]) -> list[Point]:
    """Set ``key`` on every point to ``fn(index)``; a ``None`` result leaves the key out."""
    for index, point in enumerate(points):
        for key, function in fields.items():
            value = function(index)
            if value is not None:
                point[key] = value
    return points


def _end(points: list[Point]) -> datetime:
    last = points[-1]["time"]
    assert isinstance(last, datetime)
    return last


def _time_text(value: object) -> str:
    return _stamp(value) if isinstance(value, datetime) else str(value)


def _point_xml(tag: str, point: Point) -> str:
    """Serialise a point dict as a GPX ``trkpt``/``rtept``/``wpt``."""
    parts = [f'<{tag} lat="{point["lat"]}" lon="{point["lon"]}">']
    if "ele" in point:
        parts.append(f"<ele>{point['ele']}</ele>")
    if "time" in point:
        parts.append(f"<time>{_time_text(point['time'])}</time>")
    if "name" in point:
        parts.append(f"<name>{point['name']}</name>")
    if "hdop" in point:
        parts.append(f"<hdop>{point['hdop']}</hdop>")
    tpx = "".join(f"<gpxtpx:{key}>{point[key]}</gpxtpx:{key}>" for key in ("atemp", "hr", "cad") if key in point)
    extensions = f"<gpxtpx:TrackPointExtension>{tpx}</gpxtpx:TrackPointExtension>" if tpx else ""
    for key in ("power", "speed"):
        if key in point:
            extensions += f"<{key}>{point[key]}</{key}>"
    if "pwr" in point:
        extensions += f"<pwr:PowerInWatts>{point['pwr']}</pwr:PowerInWatts>"
    if extensions:
        parts.append(f"<extensions>{extensions}</extensions>")
    parts.append(f"</{tag}>")
    return "".join(parts)


def _trk(
    segments: list[list[Point]], *, name: str | None = None, kind: str | None = None, calories: int | None = None
) -> str:
    """Serialise one GPX ``trk`` with its segments, name, ``type`` and a ``Calories`` extension."""
    parts = ["<trk>"]
    if name is not None:
        parts.append(f"<name>{name}</name>")
    if calories is not None:
        parts.append(f"<extensions><Calories>{calories}</Calories></extensions>")
    if kind is not None:
        parts.append(f"<type>{kind}</type>")
    for segment in segments:
        parts.append("<trkseg>" + "".join(_point_xml("trkpt", point) for point in segment) + "</trkseg>")
    parts.append("</trk>")
    return "".join(parts)


def _gpx(
    *body: str, creator: str = "Endurain synthetic", name: str | None = None, waypoints: list[Point] | None = None
) -> bytes:
    """Wrap ``trk``/``rte`` elements in a GPX 1.1 document with the Garmin extension namespaces."""
    metadata = f"<metadata><name>{name}</name></metadata>" if name is not None else ""
    wpts = "".join(_point_xml("wpt", point) for point in waypoints or [])
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<gpx creator="{creator}" version="1.1" xmlns="{_GPX_NS}" xmlns:gpxtpx="{_TPX_NS}" xmlns:pwr="{_PWR_NS}">'
        f"{metadata}{wpts}{''.join(body)}</gpx>"
    )
    return document.encode("utf-8")


def _single_track(points: list[Point]) -> bytes:
    return _gpx(_trk([points]))


# --------------------------------------------------------------------------------------------------------------- GPX


def _gpx_multi_track() -> bytes:
    """Two tracks with different name, type and calories, the second two hours later."""
    first = _decorate(_track(60, speed=3.0), hr=lambda i: 140 + i % 10)
    second = _decorate(_track(60, start=_START + timedelta(hours=2), speed=7.0, heading=0.0), hr=lambda i: 120 + i % 10)
    return _gpx(
        _trk([first], name="Morning Run", kind="running", calories=150),
        _trk([second], name="Evening Ride", kind="cycling", calories=200),
    )


def _gpx_two_segments_pause() -> bytes:
    """One track with two segments of about 600 m at 3 m/s, five minutes apart."""
    first = _track(200, speed=3.0)
    second = _track(200, start=_end(first) + timedelta(minutes=5), lon=_LON + 0.01, speed=3.0)
    return _gpx(_trk([first, second], name="Two segments"))


def _gpx_strava_style_ride() -> bytes:
    """A Strava export: StravaGPX creator, metadata name, cycling type, TrackPointExtension and a bare power element."""
    points = _decorate(
        _track(120, speed=7.0),
        ele=lambda i: 40 + i * 0.1,
        hr=lambda i: 130 + i % 20,
        cad=lambda i: 85 + i % 5,
        atemp=lambda _: 22,
        power=lambda i: 180 + i % 40,
    )
    return _gpx(_trk([points], name="Lunch Ride", kind="cycling"), creator="StravaGPX", name="Lunch Ride")


def _gpx_phone_app_subsecond() -> bytes:
    """A phone-app walk: millisecond timestamps, hdop, a speed extension, no heart rate and two waypoints."""
    points = _decorate(
        _track(90, start=_START + timedelta(milliseconds=250), speed=1.4),
        ele=lambda i: round(30 + math.sin(i / 10), 2),
        hdop=lambda i: 1.0 + (i % 5) / 10,
        speed=lambda _: 1.4,
    )
    waypoints: list[Point] = [
        {"lat": _LAT, "lon": _LON, "time": _START, "name": "Start"},
        {"lat": _LAT, "lon": _LON + 0.001, "time": _START + timedelta(seconds=90), "name": "Bench"},
    ]
    return _gpx(_trk([points]), creator="Phone Tracker 1.0", waypoints=waypoints)


def _gpx_power_extension() -> bytes:
    """Power from the Garmin PowerExtension ``PowerInWatts`` element."""
    points = _decorate(_track(120, speed=7.0), hr=lambda i: 140 + i % 15, pwr=lambda i: 200 + i % 50)
    return _gpx(_trk([points], name="Power ride", kind="cycling"))


def _gpx_null_island() -> bytes:
    """Every point at latitude 0, longitude 0, with times and heart rate."""
    points = _decorate(_track(60), hr=lambda i: 140 + i % 5)
    for point in points:
        point["lat"] = 0
        point["lon"] = 0
    return _single_track(points)


def _gpx_null_island_dropouts() -> bytes:
    """A normal track whose points 40 to 44 are written as 0,0 (phone GPS dropout)."""
    points = _track(120, speed=3.0)
    for point in points[40:45]:
        point["lat"] = 0
        point["lon"] = 0
    return _single_track(points)


def _gpx_untimed_points() -> bytes:
    """Every third trackpoint has no time but carries heart rate and elevation."""
    points = _decorate(_track(90), ele=lambda i: 20 + i * 0.1, hr=lambda i: 130 + i % 10)
    for point in points[::3]:
        del point["time"]
    return _single_track(points)


def _gpx_mixed_time_formats() -> bytes:
    """Times written with ``Z``, with ``+01:00`` and with no zone, interleaved (the same instants)."""
    points = _track(60)
    for index, point in enumerate(points):
        point["time"] = _stamp(_START + timedelta(seconds=index), (0, 1, None)[index % 3])
    return _single_track(points)


def _gpx_bad_sensor_values() -> bytes:
    """Heart rates NaN, -5, empty, abc and 180.7, and one elevation of nan; the rest valid."""
    bad = {3: "NaN", 6: "-5", 9: "", 12: "abc", 15: "180.7"}
    points = _decorate(
        _track(30),
        ele=lambda i: "nan" if i == 18 else 25.0,
        hr=lambda i: bad.get(i, 140),
    )
    return _single_track(points)


def _gpx_infinite_heart_rate() -> bytes:
    """One heart rate written as ``inf``."""
    points = _decorate(_track(30), hr=lambda i: "inf" if i == 10 else 140)
    return _single_track(points)


def _gpx_out_of_order() -> bytes:
    """Trackpoints 30 and 31 are swapped, so one point is out of time order."""
    points = _track(60)
    points[30], points[31] = points[31], points[30]
    return _single_track(points)


def _gpx_duplicate_timestamps() -> bytes:
    """Points 20 to 24 share one timestamp."""
    points = _track(60)
    for point in points[21:25]:
        point["time"] = points[20]["time"]
    return _single_track(points)


def _gpx_sensor_zeros() -> bytes:
    """Heart rate 0 for points 30 to 49 and cadence 0 (coasting) for points 60 to 89."""
    points = _decorate(
        _track(120, speed=7.0),
        hr=lambda i: 0 if 30 <= i < 50 else 140 + i % 10,
        cad=lambda i: 0 if 60 <= i < 90 else 85,
    )
    return _gpx(_trk([points], kind="cycling"))


def _gpx_standing_still() -> bytes:
    """Ten minutes standing at 1 Hz with +-2 m position jitter, then five minutes moving at 3 m/s."""
    jitter = _noise(7)
    still = _track(600, speed=0.0)
    for point in still:
        point["lat"] = round(_LAT + 2 * next(jitter) / _METERS_PER_DEGREE, 7)
        point["lon"] = round(_LON + 2 * next(jitter) / (_METERS_PER_DEGREE * math.cos(math.radians(_LAT))), 7)
    moving = _track(300, start=_end(still) + timedelta(seconds=1), speed=3.0)
    return _single_track(still + moving)


def _gpx_gps_spike() -> bytes:
    """A steady northbound track where point 60 jumps about 150 m sideways and back."""
    points = _track(120, speed=3.0, heading=0.0)
    points[60]["lon"] = round(_LON + 150 / (_METERS_PER_DEGREE * math.cos(math.radians(_LAT))), 7)
    return _single_track(points)


def _gpx_noisy_flat_elevation() -> bytes:
    """1800 points at 1 Hz on flat ground with deterministic +-1.5 m elevation noise."""
    noise = _noise(11)
    return _single_track(_decorate(_track(1800), ele=lambda _: round(50 + 1.5 * next(noise), 3)))


def _gpx_sparse_recording() -> bytes:
    """Smart recording: five seconds between points."""
    return _single_track(_track(120, speed=3.0, step=5.0))


def _gpx_route_only() -> bytes:
    """Only a route (``rte``/``rtept``) and waypoints, no track."""
    route_points = _track(5, speed=100.0)
    rte = "<rte><name>Planned</name>" + "".join(_point_xml("rtept", point) for point in route_points) + "</rte>"
    return _gpx(rte, waypoints=[{"lat": _LAT, "lon": _LON, "name": "Start"}])


def _gpx_single_point() -> bytes:
    """A single timed trackpoint."""
    return _single_track(_track(1))


def _gpx_malformed() -> bytes:
    """A document cut off in the middle of an element."""
    document = _single_track(_track(60))
    return document[: document.index(b"<time>", len(document) // 2) + 3]


def _gpx_not_gpx_root() -> bytes:
    """Well-formed XML whose root is not ``gpx``."""
    return b'<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>x</name></Document></kml>'


# --------------------------------------------------------------------------------------------------------------- TCX


def _tcx_point_xml(point: Point) -> str:
    """Serialise a point dict as a TCX ``Trackpoint``."""
    parts = [f"<Trackpoint><Time>{_time_text(point['time'])}</Time>"]
    if "lat" in point:
        parts.append(
            f"<Position><LatitudeDegrees>{point['lat']}</LatitudeDegrees>"
            f"<LongitudeDegrees>{point['lon']}</LongitudeDegrees></Position>"
        )
    if "alt" in point:
        parts.append(f"<AltitudeMeters>{point['alt']}</AltitudeMeters>")
    if "dist" in point:
        parts.append(f"<DistanceMeters>{point['dist']}</DistanceMeters>")
    if "hr" in point:
        parts.append(f"<HeartRateBpm><Value>{point['hr']}</Value></HeartRateBpm>")
    if "cad" in point:
        parts.append(f"<Cadence>{point['cad']}</Cadence>")
    tpx = point.get("tpx")
    if isinstance(tpx, dict):
        inner = "".join(f"<ns3:{key}>{value}</ns3:{key}>" for key, value in tpx.items())
        parts.append(f"<Extensions><ns3:TPX>{inner}</ns3:TPX></Extensions>")
    parts.append("</Trackpoint>")
    return "".join(parts)


def _lap_xml(start: datetime, points: list[Point], **summary: object) -> str:
    """Serialise a ``Lap``; ``summary`` takes total_time, distance, calories, avg_hr and avg_watts."""
    parts = [f'<Lap StartTime="{_stamp(start)}">']
    if "total_time" in summary:
        parts.append(f"<TotalTimeSeconds>{summary['total_time']}</TotalTimeSeconds>")
    if "distance" in summary:
        parts.append(f"<DistanceMeters>{summary['distance']}</DistanceMeters>")
    if "calories" in summary:
        parts.append(f"<Calories>{summary['calories']}</Calories>")
    if "avg_hr" in summary:
        parts.append(f"<AverageHeartRateBpm><Value>{summary['avg_hr']}</Value></AverageHeartRateBpm>")
    parts.append("<Intensity>Active</Intensity><TriggerMethod>Manual</TriggerMethod>")
    if points:
        parts.append("<Track>" + "".join(_tcx_point_xml(point) for point in points) + "</Track>")
    if "avg_watts" in summary:
        parts.append(f"<Extensions><ns3:LX><ns3:AvgWatts>{summary['avg_watts']}</ns3:AvgWatts></ns3:LX></Extensions>")
    parts.append("</Lap>")
    return "".join(parts)


def _activity_xml(sport: str, start: datetime, *laps: str) -> str:
    return f'<Activity Sport="{sport}"><Id>{_stamp(start)}</Id>{"".join(laps)}</Activity>'


def _tcx(*activities: str) -> bytes:
    """Wrap activities in a TCX ``TrainingCenterDatabase`` document with the activity extension namespace."""
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<TrainingCenterDatabase xmlns="{_TCX_NS}" xmlns:ns3="{_TCX_EXT_NS}">'
        f"<Activities>{''.join(activities)}</Activities></TrainingCenterDatabase>"
    )
    return document.encode("utf-8")


def _tcx_track(count: int, *, speed: float = 3.0, start: datetime = _START, heading: float = 90.0) -> list[Point]:
    """A positioned TCX track with cumulative ``dist`` and a Speed extension."""
    return _decorate(
        _track(count, speed=speed, start=start, heading=heading),
        dist=lambda i: round(speed * i, 1),
        tpx=lambda _: {"Speed": speed},
    )


def _single_lap_tcx(sport: str, points: list[Point], **summary: object) -> bytes:
    start = points[0]["time"]
    assert isinstance(start, datetime)
    return _tcx(_activity_xml(sport, start, _lap_xml(start, points, **summary)))


def _tcx_lost_fix() -> bytes:
    """A run whose trackpoints 45 to 74 have no position but keep heart rate, watts and distance."""
    points = _decorate(
        _tcx_track(120),
        hr=lambda i: 150 + i % 8,
        alt=lambda i: 30 + i * 0.05,
    )
    for index, point in enumerate(points):
        point["tpx"] = {"Speed": 3.0, "Watts": 230 + index % 10}
    for point in points[45:75]:
        del point["lat"], point["lon"]
    return _single_lap_tcx("Running", points, total_time=119, distance=357, calories=60)


def _tcx_multi_activity() -> bytes:
    """Two activities in one file, a run and then a ride an hour later."""
    run = _decorate(_tcx_track(60), hr=lambda _: 150)
    ride_start = _START + timedelta(hours=1)
    ride = _decorate(_tcx_track(60, speed=7.0, start=ride_start, heading=0.0), hr=lambda _: 130)
    return _tcx(
        _activity_xml("Running", _START, _lap_xml(_START, run, total_time=59, distance=177, calories=30)),
        _activity_xml("Biking", ride_start, _lap_xml(ride_start, ride, total_time=59, distance=413, calories=25)),
    )


def _tcx_short_laps() -> bytes:
    """Laps holding 1 and 2 trackpoints between laps of 60."""
    points = _decorate(_tcx_track(183), hr=lambda i: 140 + i % 6)
    laps = []
    index = 0
    for size in (60, 1, 60, 2, 60):
        chunk = points[index : index + size]
        start = chunk[0]["time"]
        assert isinstance(start, datetime)
        laps.append(_lap_xml(start, chunk, total_time=max(size - 1, 1), distance=3 * (size - 1)))
        index += size
    return _tcx(_activity_xml("Running", _START, *laps))


def _tcx_ride_power() -> bytes:
    """An outdoor ride with positions, altitude, Cadence, TPX Speed and Watts and LX AvgWatts on three laps."""
    points = _decorate(
        _tcx_track(150, speed=7.0, heading=0.0),
        alt=lambda i: round(40 + i * 0.1, 1),
        hr=lambda i: 135 + i % 12,
        cad=lambda i: 80 + i % 8,
    )
    for index, point in enumerate(points):
        point["tpx"] = {"Speed": 7.0, "Watts": 190 + index % 30}
    laps = []
    for index in range(0, 150, 50):
        chunk = points[index : index + 50]
        start = chunk[0]["time"]
        assert isinstance(start, datetime)
        laps.append(_lap_xml(start, chunk, total_time=49, distance=343, calories=40, avg_watts=205))
    return _tcx(_activity_xml("Biking", _START, *laps))


def _tcx_lap_summary_only() -> bytes:
    """A lap with totals and average heart rate but no ``Track``."""
    lap = _lap_xml(_START, [], total_time=1800, distance=5000, calories=300, avg_hr=150)
    return _tcx(_activity_xml("Running", _START, lap))


def _tcx_missing_watts() -> bytes:
    """TPX on every trackpoint, Watts missing on every third one, no heart rate at all."""
    points = _tcx_track(90, speed=7.0)
    for index, point in enumerate(points):
        point["tpx"] = {"Speed": 7.0} if index % 3 == 0 else {"Speed": 7.0, "Watts": 200 + index % 20}
    return _single_lap_tcx("Biking", points, total_time=89, distance=623)


def _tcx_paused() -> bytes:
    """A ten-minute gap between trackpoints inside one lap whose total time excludes the gap."""
    first = _tcx_track(60)
    second = _tcx_track(60, start=_end(first) + timedelta(minutes=10))
    for index, point in enumerate(second):
        point["dist"] = round(177 + 3.0 * index, 1)
    return _single_lap_tcx("Running", first + second, total_time=118, distance=354)


def _tcx_subsecond() -> bytes:
    """Trackpoint times with milliseconds."""
    points = _decorate(_tcx_track(60, start=_START + timedelta(milliseconds=250)), hr=lambda _: 140)
    return _single_lap_tcx("Running", points, total_time=59, distance=177)


def _tcx_other_sport_gps() -> bytes:
    """Sport ``Other`` with positions."""
    return _single_lap_tcx("Other", _tcx_track(60), total_time=59, distance=177)


def _tcx_malformed() -> bytes:
    """A document cut off in the middle of a trackpoint."""
    document = _tcx_other_sport_gps()
    return document[: document.index(b"<Trackpoint>", len(document) // 2) + 6]


# --------------------------------------------------------------------------------------------------------------- FIT

_ENUM = 0x00
_UINT8 = 0x02
_UINT16 = 0x84
_SINT32 = 0x85
_UINT32 = 0x86
_STRING = 0x07

_FILE_ID = 0
_SESSION = 18
_LAP = 19
_RECORD = 20
_EVENT = 21
_ACTIVITY = 34
_LENGTH = 101
_FIELD_DESCRIPTION = 206
_DEVELOPER_DATA_ID = 207

_SPORT_RUNNING = 1
_SPORT_CYCLING = 2
_SPORT_SWIMMING = 5
_SPORT_HIIT = 62
_SPORT_RACKET = 64
_SUB_SPORT_LAP_SWIMMING = 17
_SUB_SPORT_PADEL = 85


def _ft(second: int) -> int:
    """FIT timestamp of ``second`` seconds after the start."""
    return int((_START + timedelta(seconds=second) - fit_files._FIT_EPOCH).total_seconds())


def _semicircles(degrees: float) -> int:
    return round(degrees * 2**31 / 180)


def _pos(north_meters: float, east_meters: float = 0.0) -> list[RawField]:
    """Position fields ``north_meters``/``east_meters`` from the neutral start."""
    lat = _LAT + north_meters / _METERS_PER_DEGREE
    lon = _LON + east_meters / (_METERS_PER_DEGREE * math.cos(math.radians(_LAT)))
    return [(0, _SINT32, _semicircles(lat)), (1, _SINT32, _semicircles(lon))]


def _file_id() -> bytes:
    return fit_files.raw_message(_FILE_ID, [(0, _ENUM, 4), (1, _UINT16, 1), (4, _UINT32, _ft(0))], local_type=0)


def _rec(second: int, *fields: RawField) -> bytes:
    return fit_files.raw_message(_RECORD, [(253, _UINT32, _ft(second)), *fields], local_type=2)


def _fit_lap(start: int, elapsed: int, *fields: RawField, timer: int | None = None) -> bytes:
    return fit_files.raw_message(
        _LAP,
        [
            (253, _UINT32, _ft(start + elapsed)),
            (2, _UINT32, _ft(start)),
            (7, _UINT32, elapsed * 1000),
            (8, _UINT32, (elapsed if timer is None else timer) * 1000),
            *fields,
        ],
        local_type=1,
    )


def _fit_session(*fields: RawField, start: int = 0, elapsed: int = 60, timer: int | None = None) -> bytes:
    return fit_files.raw_message(
        _SESSION,
        [
            (253, _UINT32, _ft(start + elapsed)),
            (2, _UINT32, _ft(start)),
            (7, _UINT32, elapsed * 1000),
            (8, _UINT32, (elapsed if timer is None else timer) * 1000),
            *fields,
        ],
        local_type=3,
    )


def _sport(sport: int, sub_sport: int | None = None) -> list[RawField]:
    fields: list[RawField] = [(5, _ENUM, sport)]
    if sub_sport is not None:
        fields.append((6, _ENUM, sub_sport))
    return fields


def _event(second: int, event_type: int) -> bytes:
    """A timer event; type 0 is start, 4 is stop_all."""
    return fit_files.raw_message(
        _EVENT, [(253, _UINT32, _ft(second)), (0, _ENUM, 0), (1, _ENUM, event_type)], local_type=7
    )


def _activity_message(sessions: int) -> bytes:
    return fit_files.raw_message(
        _ACTIVITY, [(253, _UINT32, _ft(0)), (1, _UINT16, sessions), (2, _ENUM, 0), (5, _UINT32, _ft(0))], local_type=8
    )


def _sample(index: int, *, hr: int = 140, power: int | None = None, cad: int | None = None) -> list[RawField]:
    """Sensor fields for a record: heart rate, and optionally power and cadence, varying a little with ``index``."""
    fields: list[RawField] = [(3, _UINT8, hr + index % 6)]
    if cad is not None:
        fields.append((4, _UINT8, cad + index % 4))
    if power is not None:
        fields.append((7, _UINT16, power + index % 30))
    return fields


def _fit_stryd_developer_power() -> bytes:
    """Running records with Stryd-style developer fields (Power mapped to native record power 7) and no native power."""
    messages = [
        _file_id(),
        fit_files.raw_message(_DEVELOPER_DATA_ID, [(3, _UINT8, 0)], local_type=4),
    ]
    for number, name, units, native in (
        (0, "Power", "W", 7),
        (1, "Form Power", "W", None),
        (2, "Leg Spring Stiffness", "kN/m", None),
    ):
        fields: list[RawField] = [
            (0, _UINT8, 0),
            (1, _UINT8, number),
            (2, _UINT8, _UINT16),
            (3, _STRING, name),
            (8, _STRING, units),
        ]
        if native is not None:
            fields += [(14, _UINT16, 20), (15, _UINT8, native)]
        messages.append(fit_files.raw_message(_FIELD_DESCRIPTION, fields, local_type=5))
    for second in range(60):
        developer = [
            (0, 0, (240 + second % 20).to_bytes(2, "little")),
            (1, 0, (60 + second % 5).to_bytes(2, "little")),
            (2, 0, (9 + second % 3).to_bytes(2, "little")),
        ]
        fields = [
            (253, _UINT32, _ft(second)),
            *_pos(3.0 * second),
            *_sample(second, hr=150),
            (5, _UINT32, 300 * second),
            (6, _UINT16, 3_000),
        ]
        messages.append(
            fit_files.raw_message(
                _RECORD, fields, local_type=6, with_definition=second == 0, developer_fields=developer
            )
        )
    messages += [_fit_lap(0, 60), _fit_session(*_sport(_SPORT_RUNNING), (9, _UINT32, 18_000))]
    return fit_files.fit_file(*messages)


def _fit_padel() -> bytes:
    """A small padel activity: sport 64 with sub sport 85, GPS around the court, heart rate."""
    noise = _noise(5)
    messages = [_file_id()]
    for second in range(60):
        messages.append(_rec(second, *_pos(8 * next(noise), 4 * next(noise)), *_sample(second, hr=120)))
    messages += [
        _fit_lap(0, 60),
        _fit_session(*_sport(_SPORT_RACKET, _SUB_SPORT_PADEL), (11, _UINT16, 15)),
        _activity_message(1),
    ]
    return fit_files.fit_file(*messages)


def _fit_hiit() -> bytes:
    """A small HIIT activity: sport 62 (hiit), heart rate only."""
    messages = [_file_id(), *(_rec(second, *_sample(second, hr=130 + 20 * (second // 15 % 2))) for second in range(60))]
    messages += [_fit_lap(0, 60), _fit_session(*_sport(_SPORT_HIIT), (11, _UINT16, 20)), _activity_message(1)]
    return fit_files.fit_file(*messages)


def _fit_ride_power_pauses() -> bytes:
    """An outdoor ride with a five minute pause between timer stop and start; timer time is below elapsed time."""

    def ride(second: int) -> bytes:
        ridden = second if second < 120 else second - 300
        return _rec(
            second,
            *_pos(5.0 * ridden),
            *_sample(second, hr=140, power=200, cad=85),
            (5, _UINT32, 500 * ridden),
            (6, _UINT16, 5_000),
            (78, _UINT32, round((300 + 0.05 * ridden + 500) * 5)),
        )

    messages = [_file_id(), _event(0, 0), *(ride(second) for second in range(120))]
    messages += [_event(120, 4), _event(420, 0), *(ride(second) for second in range(420, 540)), _event(540, 4)]
    messages.append(_fit_lap(0, 540, (9, _UINT32, 120_000), timer=240))
    messages.append(
        _fit_session(*_sport(_SPORT_CYCLING), (9, _UINT32, 120_000), (20, _UINT16, 215), elapsed=540, timer=240)
    )
    return fit_files.fit_file(*messages)


def _fit_no_session() -> bytes:
    """Records only: no session, lap or activity message."""
    return fit_files.fit_file(
        _file_id(), *(_rec(second, *_pos(3.0 * second), *_sample(second)) for second in range(60))
    )


def _fit_session_without_start_time() -> bytes:
    """A session that carries a timestamp and elapsed time but no ``start_time``."""
    session = fit_files.raw_message(
        _SESSION,
        [(253, _UINT32, _ft(60)), (7, _UINT32, 60_000), (8, _UINT32, 60_000), *_sport(_SPORT_RUNNING)],
        local_type=3,
    )
    records = [_rec(second, *_pos(3.0 * second), *_sample(second)) for second in range(60)]
    return fit_files.fit_file(_file_id(), *records, _fit_lap(0, 60), session)


def _fit_record_without_timestamp() -> bytes:
    """One record in the middle of the file has no timestamp."""
    records = [_rec(second, *_pos(3.0 * second), *_sample(second)) for second in range(60)]
    records.insert(30, fit_files.raw_message(_RECORD, [(3, _UINT8, 150)], local_type=2))
    return fit_files.fit_file(_file_id(), *records, _fit_lap(0, 60), _fit_session(*_sport(_SPORT_RUNNING)))


def _fit_unset_clock() -> bytes:
    """Timestamps below 0x10000000: a device whose clock was never set."""
    base = 5_000
    records = [
        fit_files.raw_message(
            _RECORD, [(253, _UINT32, base + second), *_pos(3.0 * second), *_sample(second)], local_type=2
        )
        for second in range(60)
    ]
    lap = fit_files.raw_message(
        _LAP,
        [(253, _UINT32, base + 60), (2, _UINT32, base), (7, _UINT32, 60_000), (8, _UINT32, 60_000)],
        local_type=1,
    )
    session = fit_files.raw_message(
        _SESSION,
        [
            (253, _UINT32, base + 60),
            (2, _UINT32, base),
            (7, _UINT32, 60_000),
            (8, _UINT32, 60_000),
            *_sport(_SPORT_RUNNING),
        ],
        local_type=3,
    )
    return fit_files.fit_file(*records, lap, session)


def _fit_multisport_boundary() -> bytes:
    """A run then a bike session sharing second 60, with a record and a lap exactly on that second."""
    messages = [_file_id()]
    for second in range(0, 130, 10):
        # 3 m/s running to second 60, then 7 m/s riding on from where the run ended.
        north = 3.0 * second if second <= 60 else 180.0 + 7.0 * (second - 60)
        messages.append(_rec(second, *_pos(north), *_sample(second)))
    messages += [
        _fit_lap(0, 60),
        _fit_lap(60, 60),
        _fit_session(*_sport(_SPORT_RUNNING), start=0, elapsed=60),
        _fit_session(*_sport(_SPORT_CYCLING), start=60, elapsed=60),
        _activity_message(2),
    ]
    return fit_files.fit_file(*messages)


def _length(index: int, start: int, length_type: int, timer_ms: int | None) -> bytes:
    return fit_files.raw_message(
        _LENGTH,
        [
            (254, _UINT16, index),
            (2, _UINT32, _ft(start)),
            (3, _UINT32, 30_000),
            (4, _UINT32, timer_ms),
            (5, _UINT16, 18),
            (6, _UINT16, 1_200),
            (7, _ENUM, 2),
            (12, _ENUM, length_type),
        ],
        local_type=9,
    )


def _pool_session(start: int, *fields: RawField) -> bytes:
    return _fit_session(
        *_sport(_SPORT_SWIMMING, _SUB_SPORT_LAP_SWIMMING), (44, _UINT16, 2_500), *fields, start=start, elapsed=120
    )


def _fit_two_pool_sessions() -> bytes:
    """Two lap swimming sessions, each with its own active and idle lengths."""
    first = [_length(0, 0, 1, 28_000), _length(1, 30, 1, 29_000), _length(2, 60, 0, 30_000), _length(3, 90, 1, 28_000)]
    second = [
        _length(4, 300, 1, 31_000),
        _length(5, 330, 0, 30_000),
        _length(6, 360, 1, 30_000),
        _length(7, 390, 1, 27_000),
    ]
    return fit_files.fit_file(
        _file_id(),
        *first,
        _fit_lap(0, 120),
        _pool_session(0, (9, _UINT32, 7_500)),
        *second,
        _fit_lap(300, 120),
        _pool_session(300, (9, _UINT32, 7_500)),
        _activity_message(2),
    )


def _fit_lap_swim_missing_length_time() -> bytes:
    """A pool swim whose second, active length has an invalid total_timer_time."""
    lengths = [_length(0, 0, 1, 28_000), _length(1, 30, 1, None), _length(2, 60, 0, 30_000)]
    return fit_files.fit_file(_file_id(), *lengths, _pool_session(0, (9, _UINT32, 5_000)))


def _fit_gps_spike() -> bytes:
    """Sixty records at 3 m/s with record 30 displaced about 150 m sideways."""
    records = [
        _rec(second, *_pos(3.0 * second, 150.0 if second == 30 else 0.0), *_sample(second)) for second in range(60)
    ]
    return fit_files.fit_file(_file_id(), *records, _fit_lap(0, 60), _fit_session(*_sport(_SPORT_RUNNING)))


def _fit_no_records() -> bytes:
    """A manual entry: file_id, lap and session, no records."""
    return fit_files.fit_file(
        _file_id(),
        _fit_lap(0, 1800, (9, _UINT32, 500_000)),
        _fit_session(*_sport(_SPORT_RUNNING), (9, _UINT32, 500_000), (11, _UINT16, 300), elapsed=1800),
    )


def _fit_many_sessions() -> bytes:
    """Twelve short sessions in one file."""
    messages = [_file_id()]
    for number in range(12):
        start = number * 60
        messages += [
            _rec(start + second, *_pos(3.0 * (start + second)), *_sample(second)) for second in (0, 10, 20, 30)
        ]
        messages += [_fit_lap(start, 30), _fit_session(*_sport(_SPORT_RUNNING), start=start, elapsed=30)]
    messages.append(_activity_message(12))
    return fit_files.fit_file(*messages)


#: Case name (``<format>/<file name>``) to the builder of that file's bytes.
CASES: dict[str, Callable[[], bytes]] = {
    "gpx/multi_track.gpx": _gpx_multi_track,
    "gpx/two_segments_pause.gpx": _gpx_two_segments_pause,
    "gpx/strava_style_ride.gpx": _gpx_strava_style_ride,
    "gpx/phone_app_subsecond.gpx": _gpx_phone_app_subsecond,
    "gpx/power_extension.gpx": _gpx_power_extension,
    "gpx/null_island.gpx": _gpx_null_island,
    "gpx/null_island_dropouts.gpx": _gpx_null_island_dropouts,
    "gpx/untimed_points.gpx": _gpx_untimed_points,
    "gpx/mixed_time_formats.gpx": _gpx_mixed_time_formats,
    "gpx/bad_sensor_values.gpx": _gpx_bad_sensor_values,
    "gpx/infinite_heart_rate.gpx": _gpx_infinite_heart_rate,
    "gpx/out_of_order.gpx": _gpx_out_of_order,
    "gpx/duplicate_timestamps.gpx": _gpx_duplicate_timestamps,
    "gpx/sensor_zeros.gpx": _gpx_sensor_zeros,
    "gpx/standing_still.gpx": _gpx_standing_still,
    "gpx/gps_spike.gpx": _gpx_gps_spike,
    "gpx/noisy_flat_elevation.gpx": _gpx_noisy_flat_elevation,
    "gpx/sparse_recording.gpx": _gpx_sparse_recording,
    "gpx/route_only.gpx": _gpx_route_only,
    "gpx/single_point.gpx": _gpx_single_point,
    "gpx/malformed.gpx": _gpx_malformed,
    "gpx/not_gpx_root.gpx": _gpx_not_gpx_root,
    "tcx/lost_fix.tcx": _tcx_lost_fix,
    "tcx/multi_activity.tcx": _tcx_multi_activity,
    "tcx/short_laps.tcx": _tcx_short_laps,
    "tcx/ride_power.tcx": _tcx_ride_power,
    "tcx/lap_summary_only.tcx": _tcx_lap_summary_only,
    "tcx/missing_watts.tcx": _tcx_missing_watts,
    "tcx/paused.tcx": _tcx_paused,
    "tcx/subsecond.tcx": _tcx_subsecond,
    "tcx/other_sport_gps.tcx": _tcx_other_sport_gps,
    "tcx/malformed.tcx": _tcx_malformed,
    "fit/stryd_developer_power.fit": _fit_stryd_developer_power,
    "fit/padel.fit": _fit_padel,
    "fit/hiit.fit": _fit_hiit,
    "fit/ride_power_pauses.fit": _fit_ride_power_pauses,
    "fit/no_session.fit": _fit_no_session,
    "fit/session_without_start_time.fit": _fit_session_without_start_time,
    "fit/record_without_timestamp.fit": _fit_record_without_timestamp,
    "fit/unset_clock.fit": _fit_unset_clock,
    "fit/multisport_boundary.fit": _fit_multisport_boundary,
    "fit/two_pool_sessions.fit": _fit_two_pool_sessions,
    "fit/lap_swim_missing_length_time.fit": _fit_lap_swim_missing_length_time,
    "fit/gps_spike.fit": _fit_gps_spike,
    "fit/no_records.fit": _fit_no_records,
    "fit/many_sessions.fit": _fit_many_sessions,
}
