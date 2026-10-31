"""Domain constants for the profile import job."""

from enum import StrEnum

#: Domain-owned storage area holding an uploaded archive until the import job has read it.
IMPORT_STAGING_AREA = "profile_import_staging"

#: How long an import's claim and state last. It must exceed the longest legitimate import, and
#: every recorded progress renews the claim, so only a dead worker's claim runs out.
IMPORT_STATE_TTL_SECONDS = 4 * 60 * 60

#: A staged archive older than this is no import's input any more, so the sweep removes it.
IMPORT_STAGED_MAX_AGE_SECONDS = 24 * 60 * 60

#: Who asked for the import, as recorded on the event.
IMPORT_SOURCE_API = "api:profile_import"

#: Domain-owned storage area holding a finished export until the user has downloaded it.
EXPORT_STAGING_AREA = "profile_export_staging"

#: How long an export's claim and state last; the download is offered for this long.
EXPORT_STATE_TTL_SECONDS = 2 * 60 * 60

#: A staged export older than this is past its state, so the sweep removes it. It outlasts the state.
EXPORT_STAGED_MAX_AGE_SECONDS = 3 * 60 * 60

#: Who asked for the export, as recorded on the event.
EXPORT_SOURCE_API = "api:profile_export"


def export_staged_key(user_id: int) -> str:
    """Return the storage key of a user's staged export.

    One key per user: a new export replaces the last, and the claim allows one at a time.

    Args:
        user_id: The exporting user.

    Returns:
        The key within :data:`EXPORT_STAGING_AREA`.
    """
    return f"{user_id}.zip"


class ImportStatus(StrEnum):
    """Where a profile import is.

    ``RUNNING`` is the database part, which is one transaction, so a worker that dies there has
    imported nothing. ``WRITING_FILES`` starts once those rows are committed.
    """

    QUEUED = "queued"
    RUNNING = "running"
    WRITING_FILES = "writing_files"
    COMPLETED = "completed"
    FAILED = "failed"


class ImportFailure(StrEnum):
    """Stable, sanitized reasons an import can fail.

    A closed set: the underlying exception text can carry file names and parser internals, so the
    client gets a code it can translate.
    """

    INVALID_FILE = "invalid_file"
    TOO_LARGE = "too_large"
    TOO_MANY_ACTIVITIES = "too_many_activities"
    TIMED_OUT = "timed_out"
    FILES_INCOMPLETE = "files_incomplete"
    PROCESSING_FAILED = "processing_failed"


class ExportStatus(StrEnum):
    """Where a profile export is."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ExportFailure(StrEnum):
    """Stable, sanitized reasons an export can fail.

    A closed set: the underlying exception text can carry internals, so the client gets a code it
    can translate.
    """

    TIMED_OUT = "timed_out"
    PROCESSING_FAILED = "processing_failed"


#: Transfers run at once on the in-process pool: one, because an archive is held in memory.
TRANSFER_POOL_WORKERS = 1

#: Transfers the in-process pool holds, running and queued, before a new request is refused.
TRANSFER_POOL_MAX_PENDING = 3
