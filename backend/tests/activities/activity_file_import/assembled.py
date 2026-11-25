"""Helpers for tests that decode a file and assemble its activities, or assemble a recording built in code."""

import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

import modules.activities.activity_file_import.assembly as assembly
import modules.activities.activity_file_import.fit_decoder as fit_decoder
import modules.activities.activity_file_import.gpx_decoder as gpx_decoder
import modules.activities.activity_file_import.recording as recording
import modules.activities.activity_file_import.tcx_decoder as tcx_decoder
from tests._helpers.auth import MOCK_USER_ID

#: The timezone the tests give the assembly as the owner's.
OWNER_TIMEZONE = "UTC"

#: A fixed start instant for built recordings.
START = datetime(2025, 1, 1, tzinfo=UTC)


def assemble_file(
    rec: recording.Recording,
    *,
    name: str | None = None,
    timezone: str = OWNER_TIMEZONE,
    lap_distance_km: float = 1.0,
    user_id: uuid.UUID = MOCK_USER_ID,
) -> assembly.AssembledFile:
    """Assemble a recording into its multisport parent, when it has one, and its activities.

    Args:
        rec: The recording.
        name: The name the caller gives.
        timezone: The owner's timezone.
        lap_distance_km: The automatic lap distance.
        user_id: The owner.

    Returns:
        The assembled file.
    """
    return assembly.assemble(rec, user_id, name, timezone, lap_distance_km)


def assemble_recording(rec: recording.Recording, **kwargs: Any) -> list[assembly.ActivityFilePayload]:
    """Assemble every session of a recording.

    Args:
        rec: The recording.
        **kwargs: The keyword arguments of :func:`assemble_file`.

    Returns:
        One payload per session.
    """
    return assemble_file(rec, **kwargs).activities


def assemble_gpx(path: str, **kwargs: Any) -> assembly.ActivityFilePayload:
    """Decode a GPX file and assemble its one activity.

    Args:
        path: The file.
        **kwargs: The keyword arguments of :func:`assemble_recording`.

    Returns:
        The payload.
    """
    (payload,) = assemble_recording(gpx_decoder.decode_gpx(path), **kwargs)
    return payload


def assemble_tcx(path: str, **kwargs: Any) -> list[assembly.ActivityFilePayload]:
    """Decode a TCX file and assemble its activities.

    Args:
        path: The file.
        **kwargs: The keyword arguments of :func:`assemble_recording`.

    Returns:
        One payload per activity.
    """
    return assemble_recording(tcx_decoder.decode_tcx(path), **kwargs)


def assemble_fit(path: str, **kwargs: Any) -> list[assembly.ActivityFilePayload]:
    """Decode a FIT file and assemble its activities.

    Args:
        path: The file.
        **kwargs: The keyword arguments of :func:`assemble_recording`.

    Returns:
        One payload per session.
    """
    return assemble_recording(fit_decoder.decode_fit(path), **kwargs)


def samples(rows: Iterable[Mapping[str, Any]]) -> recording.Samples:
    """Build a sample table from rows of channel values.

    Args:
        rows: One mapping per sample: ``time`` plus any of the channel names of
            :meth:`recording.SamplesBuilder.append`.

    Returns:
        The table, in time order.
    """
    builder = recording.SamplesBuilder(recording.FileLimits())
    for row in rows:
        values = dict(row)
        builder.append(values.pop("time"), **values)
    return builder.build()


def session(
    rows: Iterable[Mapping[str, Any]] = (),
    *,
    sport: str | None = "running",
    start_time: datetime | None = None,
    **fields: Any,
) -> recording.Session:
    """Build a session from sample rows.

    Args:
        rows: The sample rows, see :func:`samples`.
        sport: The sport name.
        start_time: The session start; the first sample's time (else :data:`START`) when ``None``.
        **fields: Any other :class:`recording.Session` field, such as ``summary`` or ``laps``.

    Returns:
        The session.
    """
    table = samples(rows)
    start = start_time or (table.time[0] if len(table) else START)
    return recording.Session(sport=sport, start_time=start, samples=table, **fields)


def make_recording(
    *sessions: recording.Session, fmt: recording.FileFormat = "fit", **fields: Any
) -> recording.Recording:
    """Build a recording of sessions.

    Args:
        *sessions: The sessions.
        fmt: The file format.
        **fields: Any other :class:`recording.Recording` field.

    Returns:
        The recording.
    """
    return recording.Recording(format=fmt, sessions=sessions, **fields)
