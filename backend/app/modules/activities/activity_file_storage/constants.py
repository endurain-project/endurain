"""Storage addressing and lifecycle constants of the retained activity source files."""

from datetime import timedelta
from enum import StrEnum

#: Domain-owned storage namespace for activity source files. Retained files live
#: under ``files/`` (and, until the legacy files are adopted, ``processed/``) and
#: staged uploads under ``upload_staging/``; all share the area, so it is stated once
#: and the ingestion package imports it rather than repeating the string.
ACTIVITY_FILE_STORAGE_AREA = "activity_files"

#: The key root of a file with a row. ``processed/`` holds the files stored before rows existed.
FILE_KEY_PREFIX = "files"

#: A ``pending`` row or an unreferenced ``attached`` one older than this is a crashed upload or a lost
#: cleanup event, which the daily sweep resolves.
SWEEP_MIN_AGE = timedelta(days=1)

#: The most rows one sweep step or user erasure handles at a time.
BATCH_SIZE = 500


class ActivityFileState(StrEnum):
    """Where a retained file row is in its life.

    Attributes:
        PENDING: The row exists and its blob is being, or was, written; no activity references it yet.
        ATTACHED: An activity references it.
        DELETING: Its last activity is gone; the blob and then the row are being deleted.
    """

    PENDING = "pending"
    ATTACHED = "attached"
    DELETING = "deleting"
