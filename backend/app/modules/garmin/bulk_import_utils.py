"""Activity names from a Garmin export's ``summarizedActivities.json`` files.

Garmin GDPR exports include ``DI_CONNECT/DI-Connect-Fitness/
<user>_<n>_summarizedActivities.json`` files carrying the activity names the
Garmin Connect API exposes (e.g. "Auckland Cycling"). The exported FIT files
only carry the generic ``wkt_name`` field (usually "Workout"), so the names are
matched to imported activities by start time.
"""

import json
import posixpath
from collections.abc import Iterable
from datetime import datetime
from typing import Any

import core.logger as core_logger
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration

logger = core_logger.get_logger(__name__)

# Case-insensitive filename suffix identifying Garmin export summary files.
SUMMARIZED_ACTIVITIES_SUFFIX = "summarizedactivities.json"

# Maximum start-time difference for a summary entry to be considered the
# same activity as an imported file.
DEFAULT_START_TIME_TOLERANCE_S = 60


def is_summary_member(member_name: str) -> bool:
    """Whether an archive member is a Garmin export summary file.

    Args:
        member_name: The member's ``/``-separated path inside the archive.

    Returns:
        True for a ``*summarizedActivities.json`` file in any folder.
    """
    base = posixpath.basename(member_name)
    return not base.startswith(".") and base.lower().endswith(SUMMARIZED_ACTIVITIES_SUFFIX)


def _iter_summary_entries(data: Any):
    """Yield activity entry dicts from a parsed summary JSON document.

    Garmin export files wrap entries as
    ``[{"summarizedActivitiesExport": [...]}]``; a flat list of entry
    dicts is accepted as well.

    Args:
        data: Parsed JSON document.

    Yields:
        Activity entry dicts.
    """
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return
    for item in data:
        if not isinstance(item, dict):
            continue
        export_entries = item.get("summarizedActivitiesExport")
        if isinstance(export_entries, list):
            yield from (entry for entry in export_entries if isinstance(entry, dict))
        else:
            yield item


def load_summarized_activities(
    member_names: Iterable[str],
    read_member: activity_ingestion_integration.ArchiveMemberReader,
) -> dict[int, str | None]:
    """Index the activity names of every summary file in an archive.

    Args:
        member_names: Every member path in the archive.
        read_member: Reads a member of the archive by name.

    Returns:
        Activity names keyed by start time as epoch seconds (derived from
        ``startTimeGmt`` in milliseconds). A start second shared by entries with
        different names maps to None, so neither activity takes a name from it.
        Empty when no summary file is usable.
    """
    index: dict[int, str | None] = {}
    for member_name in sorted(name for name in member_names if is_summary_member(name)):
        content = read_member(member_name)
        if content is None:
            continue
        try:
            data = json.loads(content)
        except ValueError as err:
            logger.warning(
                "Bulk file import: could not parse a Garmin summary file, skipping it",
                exc_info=err,
                extra=core_logger.context(console=True, file=member_name),
            )
            continue

        for entry in _iter_summary_entries(data):
            start_ms = entry.get("startTimeGmt")
            name = entry.get("name")
            if not isinstance(start_ms, (int, float)) or not name:
                continue
            start_s = int(start_ms) // 1000
            if start_s in index:
                if index[start_s] != str(name):
                    logger.warning(
                        "Bulk file import: two Garmin summary entries share a start second, naming neither",
                        extra=core_logger.context(console=True, file=member_name, start_time=start_s),
                    )
                    index[start_s] = None
                continue
            index[start_s] = str(name)

    logger.info(
        "Bulk file import: loaded activity names from Garmin summary files",
        extra=core_logger.context(console=True, names=sum(name is not None for name in index.values())),
    )
    return index


def find_name_for_start_time(
    index: dict[int, str | None],
    start_time: datetime,
    tolerance_s: int = DEFAULT_START_TIME_TOLERANCE_S,
) -> str | None:
    """Find the summary name matching an activity start time.

    Args:
        index: Lookup built by :func:`load_summarized_activities`.
        start_time: Activity start time (timezone-aware).
        tolerance_s: Maximum allowed difference in seconds.

    Returns:
        The name of the entry with the exact start second, else of the only
        entry within ``tolerance_s``. None when nothing matches, when the
        matching second is shared by several entries, or when several entries
        are within range, since activities started close together (a brick
        workout, a split recording) could otherwise take each other's names.
    """
    if not index:
        return None
    epoch = int(start_time.timestamp())

    if epoch in index:
        return index[epoch]

    candidates = [name for entry_epoch, name in index.items() if abs(entry_epoch - epoch) <= tolerance_s]
    return candidates[0] if len(candidates) == 1 else None
