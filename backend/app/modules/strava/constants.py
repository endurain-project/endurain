"""Strava constants and closed vocabularies."""

from enum import StrEnum

import core.job_status as core_job_status

PROVIDER_NAME = "strava"

#: The name the Strava export layout registers under with bulk import.
BULK_IMPORT_FORMAT_NAME = "strava"

#: The member of a Strava export that lists its activities.
BULK_IMPORT_ACTIVITIES_FILE = "activities.csv"

#: The directory under ``FILES_DIR`` each user's Strava export is dropped in, one subdirectory per user.
BULK_IMPORT_DIR_NAME = "strava_import"

#: The name a shoe with no name in a Strava gear export gets, followed by a number that keeps it unique.
UNNAMED_SHOE_NICKNAME_PREFIX = "Unnamed Shoe "

#: Largest gear CSV accepted: a gear list is a few hundred rows at most.
GEAR_CSV_MAX_BYTES = 2 * 1024 * 1024

#: The OAuth scopes a Strava link needs, comma-separated as Strava lists them; the web client requests exactly these.
REQUIRED_OAUTH_SCOPES = ("read", "profile:read_all", "activity:read_all")

#: Seconds a request to Strava may take before it is abandoned; stravalib sets no timeout of its own.
HTTP_TIMEOUT_SECONDS = 30

#: Seconds the user has to finish the Strava consent screen before the one-time state expires.
OAUTH_STATE_TTL_SECONDS = 10 * 60

# Bytes of randomness in a server-issued OAuth state; a state shorter than its encoding is refused.
OAUTH_STATE_BYTES = 32
OAUTH_STATE_MIN_LENGTH = 32

#: Seconds a token refresh claim lasts if its holder dies before releasing it.
TOKEN_REFRESH_CLAIM_TTL_SECONDS = 60

# Activities an unlink deletes per transaction, so a large account never holds every row lock at once.
UNLINK_DELETE_BATCH_SIZE = 500

#: Users whose Strava data is deleted per pass of the revoked-access job.
REVOKED_DELETE_PAGE_SIZE = 50

#: Event source recorded on a queued sync.
SYNC_SOURCE_API = "api:strava_sync"


class SyncKind(StrEnum):
    """What a queued Strava sync does."""

    LINK = "link"
    GEAR = "gear"
    UNLINK = "unlink"


#: Seconds a client waits before polling a queued sync of each kind: a link is one token exchange.
SYNC_POLL_SECONDS: dict[SyncKind, int] = {SyncKind.LINK: 2, SyncKind.GEAR: 5, SyncKind.UNLINK: 5}


def job_name(kind: SyncKind) -> str:
    """Name a queued sync in the realtime hints; the web client follows the same names.

    Args:
        kind: What the sync does.

    Returns:
        The job name, such as ``strava:link``.
    """
    return f"{PROVIDER_NAME}:{kind.value}"


#: Where a queued sync is; shared by every provider's sync state.
SyncStatus = core_job_status.JobState
