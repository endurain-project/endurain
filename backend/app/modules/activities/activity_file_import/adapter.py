"""Adapt parser output dicts into the canonical :class:`ParsedActivity` contract.

The file parsers (``gpx_parser`` / ``tcx_parser`` / ``fit_parser``) build a
``parsed_info`` dict (``parser_utils.ActivityFilePayload``) shaped like::

    {
        "activity": <ActivityCore>,
        "laps": [...] | None,
        "sets": [...] | None,
        "workout_steps": [...] | None,
        "is_heart_rate_set": bool, "hr_waypoints": [...],
        "is_power_set": bool, "power_waypoints": [...],
        ...
    }

This module converts that dict into a typed
:class:`~modules.activities.activity.contracts.ParsedActivity`. It lives here,
next to the parsers, because producing the canonical shape is part of parsing:
the ingestion core receives :class:`ParsedActivity` objects and never sees the
intermediate dict.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Literal

import core.logger as core_logger
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity_file_import.parser_utils as activity_file_import_parser_utils
import modules.activities.activity_streams.constants as activity_streams_constants
import modules.activities.activity_streams.contracts as activity_streams_contracts
import modules.activities.computation as activities_computation

logger = core_logger.get_logger(__name__)

#: A payload key naming whether a stream is set.
type _StreamFlagKey = Literal[
    "is_heart_rate_set",
    "is_power_set",
    "is_cadence_set",
    "is_elevation_set",
    "is_velocity_set",
    "is_lat_lon_set",
    "is_temperature_set",
]

#: A payload key holding a stream's waypoints.
type _StreamWaypointsKey = Literal[
    "hr_waypoints",
    "power_waypoints",
    "cad_waypoints",
    "ele_waypoints",
    "vel_waypoints",
    "pace_waypoints",
    "lat_lon_waypoints",
    "temp_waypoints",
]

# stream_type -> (is-set flag key, waypoints key) in the parser output dict.
# Mirrors the mapping the parsers populate. Stream types 5 and 6 both derive from
# ``is_velocity_set`` (speed and pace share the velocity flag).
_STREAM_MAPPING: dict[int, tuple[_StreamFlagKey, _StreamWaypointsKey]] = {
    activity_streams_constants.STREAM_TYPE_HR: ("is_heart_rate_set", "hr_waypoints"),
    activity_streams_constants.STREAM_TYPE_POWER: ("is_power_set", "power_waypoints"),
    activity_streams_constants.STREAM_TYPE_CADENCE: ("is_cadence_set", "cad_waypoints"),
    activity_streams_constants.STREAM_TYPE_ELEVATION: ("is_elevation_set", "ele_waypoints"),
    activity_streams_constants.STREAM_TYPE_SPEED: ("is_velocity_set", "vel_waypoints"),
    activity_streams_constants.STREAM_TYPE_PACE: ("is_velocity_set", "pace_waypoints"),
    activity_streams_constants.STREAM_TYPE_MAP: ("is_lat_lon_set", "lat_lon_waypoints"),
    activity_streams_constants.STREAM_TYPE_TEMPERATURE: ("is_temperature_set", "temp_waypoints"),
}


def _stream_waypoints(stream_type: int, waypoints: Sequence[Mapping[str, Any]]) -> Sequence[Mapping[str, Any]]:
    """Return the waypoints to store, smoothing the elevation stream.

    Args:
        stream_type: Stream type of the waypoints.
        waypoints: Raw parsed waypoints.

    Returns:
        Smoothed waypoints for the elevation stream, unchanged otherwise.
    """
    if stream_type == activity_streams_constants.STREAM_TYPE_ELEVATION:
        return activities_computation.smooth_elevation_stream(waypoints)
    return waypoints


def parsed_info_to_parsed_activity[LapT](
    parsed_info: activity_file_import_parser_utils.ActivityFilePayload[LapT],
) -> activity_contracts.ParsedActivity:
    """Convert a parser output dict into a :class:`ParsedActivity`.

    Provenance (:class:`ImportSource`) is deliberately *not* set here: a parser
    knows what the file contains, not where it came from or what its content hash
    is. The ingestion pipeline attaches that after parsing.

    Args:
        parsed_info: The dict a parser builds for one activity (for a
            multi-activity ``.fit``, one entry from
            ``fit_parser.create_activity_objects``). Must contain an
            ``"activity"`` key.

    Returns:
        The canonical parsed activity, with one
        :class:`~modules.activities.activity_streams.contracts.ParsedStream` per
        stream that the parser flagged as set.
    """
    streams = [
        activity_streams_contracts.ParsedStream(
            stream_type=stream_type,
            stream_waypoints=_stream_waypoints(stream_type, parsed_info.get(waypoints_key, [])),
        )
        for stream_type, (is_set_key, waypoints_key) in _STREAM_MAPPING.items()
        if parsed_info.get(is_set_key, False)
    ]

    laps = parsed_info.get("laps")
    sets = parsed_info.get("sets")
    workout_steps = parsed_info.get("workout_steps")
    components: dict[str, object] = {
        "streams": streams,
        "laps": laps,
        "sets": sets,
        "workout_steps": workout_steps,
    }
    parsed = activity_contracts.ParsedActivity(
        activity=parsed_info["activity"],
        components=components,
    )
    # What the parser actually produced, before anything is persisted — the first
    # thing to check when an imported activity is missing a chart or its laps.
    logger.debug(
        "Adapted parser output into a ParsedActivity",
        extra=core_logger.context(
            stream_types=[stream.stream_type for stream in streams],
            component_counts={
                "streams": len(streams),
                "laps": len(laps) if laps else 0,
                "sets": len(sets) if sets else 0,
                "workout_steps": len(workout_steps) if workout_steps else 0,
            },
        ),
    )
    return parsed
