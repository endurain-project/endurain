"""Utilities for enriching bulk imports with Garmin export metadata.

Garmin GDPR exports include ``DI_CONNECT/DI-Connect-Fitness/
*_summarizedActivities.json`` files carrying the activity names the
Garmin Connect API exposes (e.g. "Auckland Cycling"). Bulk-imported
FIT files only carry the generic ``wkt_name`` field (usually
"Workout"), so activity names differed between bulk import and Garmin
Connect sync (issue #492). When such a summary file is present in the
bulk import directory, its names are matched to imported activities by
start time.
"""

import json
import os
from datetime import UTC, datetime
from typing import Any

import core.logger as core_logger

# Case-insensitive filename suffix identifying Garmin export summary files.
SUMMARIZED_ACTIVITIES_SUFFIX = "summarizedactivities.json"

# Maximum start-time difference for a summary entry to be considered the
# same activity as an imported file.
DEFAULT_START_TIME_TOLERANCE_S = 60


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


def load_summarized_activities(bulk_import_dir: str) -> dict[int, dict]:
    """Index Garmin export summary files found in a directory.

    Scans ``bulk_import_dir`` for ``*summarizedActivities.json`` files
    and builds a lookup of activity metadata keyed by start time.

    Args:
        bulk_import_dir: Directory to scan (the bulk import folder).

    Returns:
        Dict keyed by activity start time as epoch seconds (derived
        from ``startTimeGmt`` in milliseconds), each value a dict with
        ``name`` and ``activityId``. Empty when no usable summary file
        is present.
    """
    index: dict[int, dict] = {}
    try:
        file_names = os.listdir(bulk_import_dir)
    except OSError:
        return index

    for file_name in sorted(file_names):
        if not file_name.lower().endswith(SUMMARIZED_ACTIVITIES_SUFFIX):
            continue
        file_path = os.path.join(bulk_import_dir, file_name)
        try:
            with open(file_path, encoding="utf-8") as summary_file:
                data = json.load(summary_file)
        except (OSError, ValueError) as err:
            core_logger.print_to_log_and_console(
                f"Bulk file import: Could not parse Garmin summary file {file_path} - {err}. Skipping it.",
                "warning",
            )
            continue

        for entry in _iter_summary_entries(data):
            start_ms = entry.get("startTimeGmt")
            name = entry.get("name")
            if not isinstance(start_ms, (int, float)) or not name:
                continue
            index[int(start_ms) // 1000] = {
                "name": str(name),
                "activityId": entry.get("activityId"),
            }

    if index:
        core_logger.print_to_log_and_console(
            f"Bulk file import: Loaded {len(index)} activity name(s) from Garmin summarizedActivities file(s).",
            "info",
        )
    return index


def find_summary_for_start_time(
    index: dict[int, dict],
    start_time: datetime | str | None,
    tolerance_s: int = DEFAULT_START_TIME_TOLERANCE_S,
) -> dict | None:
    """Find the summary entry matching an activity start time.

    Args:
        index: Lookup built by :func:`load_summarized_activities`.
        start_time: Activity start time — a datetime or ISO 8601
            string (naive values are assumed UTC, matching the import
            parsers' output).
        tolerance_s: Maximum allowed difference in seconds.

    Returns:
        The matching entry dict, preferring an exact epoch match and
        falling back to the nearest entry within ``tolerance_s``, or
        None when nothing matches.
    """
    if not index or start_time is None:
        return None

    if isinstance(start_time, str):
        try:
            start_time = datetime.fromisoformat(start_time)
        except ValueError:
            return None
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=UTC)
    epoch = int(start_time.timestamp())

    exact = index.get(epoch)
    if exact is not None:
        return exact

    best: dict | None = None
    best_delta = tolerance_s + 1
    for entry_epoch, entry in index.items():
        delta = abs(entry_epoch - epoch)
        if delta <= tolerance_s and delta < best_delta:
            best, best_delta = entry, delta
    return best
