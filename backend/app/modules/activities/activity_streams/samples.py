"""Pure maths on an activity's columnar samples: conversion of stored waypoint streams, downsampling and pace.

No session, no ORM and no other module: every function takes values and returns values.
"""

import datetime
from collections.abc import Sequence
from typing import Any

import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.activity_streams.schema as activity_streams_schema

_ONE_MILLISECOND = datetime.timedelta(milliseconds=1)

#: The samples channel and the waypoint key of each stored stream type that feeds one value channel. Pace has no
#: channel (it is derived from speed) and the map stream feeds two, so neither is listed.
_VALUE_STREAMS: dict[int, tuple[str, str]] = {
    activity_streams_constants.STREAM_TYPE_HR: ("heart_rate", "hr"),
    activity_streams_constants.STREAM_TYPE_POWER: ("power", "power"),
    activity_streams_constants.STREAM_TYPE_CADENCE: ("cadence", "cad"),
    activity_streams_constants.STREAM_TYPE_ELEVATION: ("elevation", "ele"),
    activity_streams_constants.STREAM_TYPE_SPEED: ("speed", "vel"),
    activity_streams_constants.STREAM_TYPE_TEMPERATURE: ("temperature", "temp"),
}


def _offset_ms(time: object, start_time: datetime.datetime) -> int | None:
    """Read a stored waypoint's ``time`` as milliseconds from the activity start.

    Args:
        time: A UTC ``YYYY-MM-DDTHH:MM:SS`` string (a naive one is UTC), or seconds from the start as a number, as a
            stream imported from Strava stores it.
        start_time: The activity's start, timezone-aware UTC.

    Returns:
        The offset, or ``None`` when the waypoint has no usable time.
    """
    if isinstance(time, str):
        try:
            instant = datetime.datetime.fromisoformat(time)
        except ValueError:
            return None
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=datetime.UTC)
        return (instant - start_time) // _ONE_MILLISECOND
    if isinstance(time, int | float) and not isinstance(time, bool):
        return round(time * 1000)
    return None


def _number(value: object) -> float | None:
    """Return a stored value as a float, or ``None`` when the waypoint has none.

    Args:
        value: The waypoint's value.

    Returns:
        The value as a float, or ``None`` for a missing or non-numeric value.
    """
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def samples_from_streams(
    rows: Sequence[activity_streams_schema.ActivityStreamsBase],
    start_time: datetime.datetime,
) -> activity_streams_contracts.ParsedSamples | None:
    """Turn an activity's stored waypoint streams into columnar samples on one timeline.

    The timeline is the union of the instants of all the streams, in milliseconds from ``start_time``. A stream
    stores only the samples that have its value, so a channel is ``None`` at an instant its stream has no waypoint
    for. The stored pace stream is dropped: pace is derived from speed. A waypoint with no usable ``time`` is left
    out, and a stream of an unknown type is ignored.

    A file stamps its waypoints to the whole second, so a recording faster than 1 Hz stores several waypoints under
    one stamp. They stay several samples, in the order stored, all at the stamp's offset. Across streams the k-th
    waypoint of a stamp in each stream is taken to be the same sample, which is exact when the streams were cut from
    the same recorded samples, as they are for a file. A stream that lacks some of a stamp's samples lines up with
    the first ones.

    Args:
        rows: The activity's stored streams.
        start_time: The activity's start; a naive value is read as UTC.

    Returns:
        The samples, or ``None`` when no stream holds a value for a channel.
    """
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=datetime.UTC)

    # Each stream's waypoints keyed by (offset, occurrence of that offset within the stream), with the channel values.
    keyed: list[dict[tuple[int, int], dict[str, float | None]]] = []
    for row in rows:
        if row.stream_type == activity_streams_constants.STREAM_TYPE_MAP:
            keys = {"latitude": "lat", "longitude": "lon"}
        elif row.stream_type in _VALUE_STREAMS:
            name, key = _VALUE_STREAMS[row.stream_type]
            keys = {name: key}
        else:
            continue
        seen: dict[int, int] = {}
        stream: dict[tuple[int, int], dict[str, float | None]] = {}
        for waypoint in row.stream_waypoints:
            offset = _offset_ms(waypoint.get("time"), start_time)
            if offset is None:
                continue
            occurrence = seen.get(offset, 0)
            seen[offset] = occurrence + 1
            stream[(offset, occurrence)] = {name: _number(waypoint.get(key)) for name, key in keys.items()}
        keyed.append(stream)

    timeline = sorted({key for stream in keyed for key in stream})
    index = {key: i for i, key in enumerate(timeline)}
    channels: dict[str, list[float | None]] = {}
    for stream in keyed:
        for instant, values in stream.items():
            for name, value in values.items():
                channels.setdefault(name, [None] * len(timeline))[index[instant]] = value

    latitude = channels.pop("latitude", [None] * len(timeline))
    longitude = channels.pop("longitude", [None] * len(timeline))
    # A position needs both coordinates.
    positioned = [lat is not None and lon is not None for lat, lon in zip(latitude, longitude, strict=True)]
    channels["latitude"] = [lat if has else None for lat, has in zip(latitude, positioned, strict=True)]
    channels["longitude"] = [lon if has else None for lon, has in zip(longitude, positioned, strict=True)]

    present: dict[str, Any] = {
        name: values for name, values in channels.items() if any(value is not None for value in values)
    }
    if not present:
        return None
    return activity_streams_contracts.ParsedSamples(offsets_ms=[offset for offset, _ in timeline], **present)


def pace_from_speed(speed: Sequence[float | None]) -> list[float | None]:
    """Derive pace from speed.

    Args:
        speed: Speed per sample, in m/s.

    Returns:
        Pace per sample, in s/m; ``None`` where the speed is missing or not above 0.
    """
    return [1 / value if value is not None and value > 0 else None for value in speed]


def _mean(values: Sequence[float | None]) -> float | None:
    """Return the mean of the values that exist.

    Args:
        values: Values, ``None`` where a sample has none.

    Returns:
        The mean, or ``None`` when no value exists.
    """
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None


def downsample(
    samples: activity_streams_contracts.ParsedSamples, max_points: int
) -> activity_streams_contracts.ParsedSamples:
    """Reduce samples to at most ``max_points`` by averaging them over equal-time buckets.

    ``[first offset, last offset]`` is split into ``max_points`` buckets of equal duration and each bucket that holds a
    sample becomes one: its offset is the mean of its samples' offsets, rounded to a whole millisecond, and a channel
    is the mean of its samples' values that exist (``None`` when none does). Latitude and longitude are averaged
    together, over the samples that have both. A pause leaves empty buckets, which are dropped.

    Args:
        samples: The samples, in time order.
        max_points: The most samples to return, at least 2.

    Returns:
        The samples themselves when there are no more than ``max_points``, else the averaged samples.
    """
    offsets = samples.offsets_ms
    if len(offsets) <= max_points:
        return samples

    first = offsets[0]
    span = offsets[-1] - first
    buckets: dict[int, list[int]] = {}
    for i, offset in enumerate(offsets):
        bucket = min((offset - first) * max_points // span, max_points - 1) if span else 0
        buckets.setdefault(bucket, []).append(i)
    groups = [buckets[bucket] for bucket in sorted(buckets)]

    def means(channel: Sequence[float | None] | None) -> list[float | None] | None:
        return None if channel is None else [_mean([channel[i] for i in group]) for group in groups]

    latitude: list[float | None] | None = None
    longitude: list[float | None] | None = None
    if samples.latitude is not None and samples.longitude is not None:
        latitude, longitude = [], []
        for group in groups:
            both = [i for i in group if samples.latitude[i] is not None and samples.longitude[i] is not None]
            latitude.append(_mean([samples.latitude[i] for i in both]))
            longitude.append(_mean([samples.longitude[i] for i in both]))
    return activity_streams_contracts.ParsedSamples(
        offsets_ms=[round(sum(offsets[i] for i in group) / len(group)) for group in groups],
        latitude=latitude,
        longitude=longitude,
        elevation=means(samples.elevation),
        heart_rate=means(samples.heart_rate),
        power=means(samples.power),
        cadence=means(samples.cadence),
        speed=means(samples.speed),
        temperature=means(samples.temperature),
    )
