"""Adapt parser output dicts into the canonical :class:`ParsedActivity` contract.

``assembly`` builds a ``parsed_info`` dict (``assembly.ActivityFilePayload``) for each session of a decoded
file, shaped like::

    {
        "activity": <ActivityCore>,
        "laps": [...] | None,
        "sets": [...] | None,
        "workout_steps": [...] | None,
        "samples": <ParsedSamples> | None,
    }

This module converts that dict into a typed
:class:`~modules.activities.activity.contracts.ParsedActivity`. It lives here,
next to the parsers, because producing the canonical shape is part of parsing:
the ingestion core receives :class:`ParsedActivity` objects and never sees the
intermediate dict.
"""

import core.logger as core_logger
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity_file_import.assembly as activity_file_import_assembly

logger = core_logger.get_logger(__name__)


def parsed_info_to_parsed_activity(
    parsed_info: activity_file_import_assembly.ActivityFilePayload,
) -> activity_contracts.ParsedActivity:
    """Convert a parser output dict into a :class:`ParsedActivity`.

    Provenance (:class:`ImportSource`) is deliberately *not* set here: the file
    parsing knows what the file contains, not where it came from or what its content hash
    is. The ingestion pipeline attaches that after parsing.

    Args:
        parsed_info: The payload ``assembly.assemble`` builds for one session.

    Returns:
        The canonical parsed activity, with the columnar samples assembly built, if any.
    """
    samples = parsed_info.get("samples")
    laps = parsed_info.get("laps")
    sets = parsed_info.get("sets")
    workout_steps = parsed_info.get("workout_steps")
    components: dict[str, object] = {
        "samples": samples,
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
            component_counts={
                "samples": len(samples.offsets_ms) if samples else 0,
                "laps": len(laps) if laps else 0,
                "sets": len(sets) if sets else 0,
                "workout_steps": len(workout_steps) if workout_steps else 0,
            },
        ),
    )
    return parsed
