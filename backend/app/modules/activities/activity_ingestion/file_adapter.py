"""Adapt parser output dicts into the canonical :class:`ParsedActivity` contract.

The file parsers (``utils_gpx`` / ``utils_tcx`` / ``utils_fit``) return an untyped
``parsed_info`` dict shaped like::

    {
        "activity": <Activity schema>,
        "laps": [...] | None,
        "sets": [...] | None,
        "workout_steps": [...] | None,
        "is_heart_rate_set": bool, "hr_waypoints": [...],
        "is_power_set": bool, "power_waypoints": [...],
        ...
    }

This module converts that dict into a typed
:class:`~modules.activities.activity.schema.ParsedActivity` so the activities core can
persist it without knowing anything about file formats.
"""

import core.logger as core_logger
import modules.activities.activity.contracts as activities_contracts

logger = core_logger.get_logger(__name__)

# stream_type -> (is-set flag key, waypoints key) in the parser output dict.
# Mirrors the mapping the parsers populate. Stream types 5 and 6 both derive from
# ``is_velocity_set`` (speed and pace share the velocity flag).
_STREAM_MAPPING: dict[int, tuple[str, str]] = {
    1: ("is_heart_rate_set", "hr_waypoints"),
    2: ("is_power_set", "power_waypoints"),
    3: ("is_cadence_set", "cad_waypoints"),
    4: ("is_elevation_set", "ele_waypoints"),
    5: ("is_velocity_set", "vel_waypoints"),
    6: ("is_velocity_set", "pace_waypoints"),
    7: ("is_lat_lon_set", "lat_lon_waypoints"),
    8: ("is_temperature_set", "temp_waypoints"),
}


def parsed_info_to_parsed_activity(
    parsed_info: dict,
    source: activities_contracts.ImportSource | None = None,
) -> activities_contracts.ParsedActivity:
    """Convert a parser output dict into a :class:`ParsedActivity`.

    Args:
        parsed_info: The dict returned by a file parser (or a per-activity entry
            produced by ``utils_fit.create_activity_objects`` for multi-activity
            ``.fit`` files). Must contain an ``"activity"`` key.
        source: Optional provenance describing where the activity came from.

    Returns:
        The canonical parsed activity, with one
        :class:`~modules.activities.activity.schema.ParsedStream` per stream that
        the parser flagged as set.
    """
    streams = [
        activities_contracts.ParsedStream(
            stream_type=stream_type,
            stream_waypoints=parsed_info.get(waypoints_key, []),
        )
        for stream_type, (is_set_key, waypoints_key) in _STREAM_MAPPING.items()
        if (is_set_key(parsed_info) if callable(is_set_key) else parsed_info.get(is_set_key, False))
    ]

    parsed = activities_contracts.ParsedActivity(
        activity=parsed_info["activity"],
        streams=streams,
        laps=parsed_info.get("laps"),
        sets=parsed_info.get("sets"),
        workout_steps=parsed_info.get("workout_steps"),
        source=source,
    )
    # What the parser actually produced, before anything is persisted — the first
    # thing to check when an imported activity is missing a chart or its laps.
    logger.debug(
        "Adapted parser output into a ParsedActivity",
        extra=core_logger.context(
            source_kind=source.kind if source is not None else None,
            stream_types=[stream.stream_type for stream in streams],
            lap_count=len(parsed.laps) if parsed.laps else 0,
            set_count=len(parsed.sets) if parsed.sets else 0,
            workout_step_count=len(parsed.workout_steps) if parsed.workout_steps else 0,
        ),
    )
    return parsed
