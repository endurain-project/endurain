"""Cleans a decoded session's samples of what a device or an app wrote wrongly, before anything is computed from them.

The decoders keep what the file says; this module drops what no athlete could have done, so every later stage (streams,
distance, speeds, elevation) works from trustworthy samples. It is pure: a session goes in, a cleaned session comes out.

The rules, applied in this order to each session's sample table:

* Rows with the same time become one row; per channel the first value in file order that is not ``None`` wins, and the
  position is taken as a pair, from the first row that has both coordinates.
* A position of exactly (0, 0), "null island", is a GPS that has no fix: the row loses its position, not its other
  channels.
* A heart rate of 0 is a dropout of the strap, not a heart that stopped: the row loses it. Cadence 0 and power 0 are
  real (coasting, standing still) and stay.
* A speed above the sport's cap is not recorded speed: the device speed of that row is dropped, and so is a position
  that implies such a speed from the last kept position, which is how a one-sample GPS jump is removed while the track
  goes on from the point before it. The first position is only provisional: a watch's first fix can be where it last
  saw the sky, so when the step away from it is too fast but the next position agrees with the one after it, the first
  fix is the one dropped. The device ``distance`` is never touched.
"""

import dataclasses

from geopy.distance import great_circle

import modules.activities.activity.constants as activity_constants
import modules.activities.activity_file_import.recording as activity_file_import_recording

#: The fastest speed in metres per second a sport bucket can plausibly record.
_FOOT_MAX_SPEED = 12.0
_BIKE_MAX_SPEED = 35.0
_WATER_MAX_SPEED = 6.0
_OTHER_MAX_SPEED = 50.0

_FOOT_SPORTS = ("run", "walk", "hike")
_WATER_SPORTS = ("swim", "rowing", "kayaking", "stand_up_paddling", "surf", "windsurf", "sailing")


def _max_speed(sport: str | None) -> float:
    """Return the speed cap of a session's sport.

    Args:
        sport: The session's sport name, ``None`` when the file names none.

    Returns:
        The cap in metres per second.
    """
    if not sport:
        return _OTHER_MAX_SPEED
    activity_type = activity_constants.define_activity_type(sport)
    by_sport = activity_constants.ACTIVITY_TYPES_BY_SPORT
    if any(activity_type in by_sport[name] for name in _FOOT_SPORTS):
        return _FOOT_MAX_SPEED
    if activity_type in by_sport["bike"]:
        return _BIKE_MAX_SPEED
    if any(activity_type in by_sport[name] for name in _WATER_SPORTS):
        return _WATER_MAX_SPEED
    return _OTHER_MAX_SPEED


def _first_known[T](values: list[T | None], rows: list[int]) -> T | None:
    """Return the first value among the given rows that is not ``None``.

    Args:
        values: One channel's column.
        rows: The row indexes to look at, in file order.

    Returns:
        The first value that is not ``None``, ``None`` when there is none.
    """
    for row in rows:
        if values[row] is not None:
            return values[row]
    return None


def _merge_duplicate_times(samples: activity_file_import_recording.Samples) -> activity_file_import_recording.Samples:
    """Merge rows that share a time into one row, the first known value of each channel winning.

    Args:
        samples: The table, in time order.

    Returns:
        The table with one row per time.
    """
    groups: list[list[int]] = []
    for row, time in enumerate(samples.time):
        if groups and samples.time[groups[-1][0]] == time:
            groups[-1].append(row)
        else:
            groups.append([row])
    if len(groups) == len(samples):
        return samples
    columns = {
        field.name: tuple(_first_known(list(getattr(samples, field.name)), group) for group in groups)
        for field in dataclasses.fields(samples)
        if field.name not in ("time", "lat", "lon")
    }
    positions = [
        next(
            (
                (samples.lat[row], samples.lon[row])
                for row in group
                if samples.lat[row] is not None and samples.lon[row] is not None
            ),
            (None, None),
        )
        for group in groups
    ]
    return activity_file_import_recording.Samples(
        time=tuple(samples.time[group[0]] for group in groups),
        lat=tuple(lat for lat, _ in positions),
        lon=tuple(lon for _, lon in positions),
        **columns,
    )


def clean_session(session: activity_file_import_recording.Session) -> activity_file_import_recording.Session:
    """Return the session with its samples cleaned.

    Args:
        session: The decoded session.

    Returns:
        The session with duplicate times merged, null-island positions, zero heart rates and speeds above the sport's
        cap removed; everything else is as it was.
    """
    samples = _merge_duplicate_times(session.samples)
    cap = _max_speed(session.sport)
    lat = list(samples.lat)
    lon = list(samples.lon)
    heart_rate = [None if value == 0 else value for value in samples.heart_rate]
    speed = [None if value is not None and value > cap else value for value in samples.speed]

    for row in range(len(samples)):
        if lat[row] == 0.0 and lon[row] == 0.0:
            lat[row] = lon[row] = None
    positioned = [row for row in range(len(samples)) if lat[row] is not None and lon[row] is not None]

    def too_fast(first: int, second: int) -> bool:
        """Return whether going from one positioned row to a later one is faster than the sport's cap."""
        metres = great_circle((lat[first], lon[first]), (lat[second], lon[second])).meters
        return metres / (samples.time[second] - samples.time[first]).total_seconds() > cap

    kept: int | None = None
    confirmed = False
    for index, row in enumerate(positioned):
        if kept is None or not too_fast(kept, row):
            confirmed = kept is not None
            kept = row
            continue
        following = positioned[index + 1] if index + 1 < len(positioned) else None
        if not confirmed and following is not None and not too_fast(row, following):
            # The first fix is the odd one out: the track from here on agrees with itself.
            lat[kept] = lon[kept] = None
            kept = row
            confirmed = True
            continue
        lat[row] = lon[row] = None

    cleaned = dataclasses.replace(
        samples, lat=tuple(lat), lon=tuple(lon), heart_rate=tuple(heart_rate), speed=tuple(speed)
    )
    return dataclasses.replace(session, samples=cleaned)
