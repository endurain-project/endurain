"""Strava constants and closed vocabularies."""

from enum import StrEnum

import core.attempt_state as core_attempt_state

PROVIDER_NAME = "strava"

#: The name the Strava export layout registers under with bulk import.
BULK_IMPORT_FORMAT_NAME = "strava"

#: The job names a Strava link's and unlink's realtime hints carry; the web client follows the same names.
LINK_JOB = "strava:link"
UNLINK_JOB = "strava:unlink"

#: Seconds a request to Strava may take before it is abandoned; stravalib sets no timeout of its own.
HTTP_TIMEOUT_SECONDS = 30

#: Seconds the user has to finish the Strava consent screen before the one-time state expires.
OAUTH_STATE_TTL_SECONDS = 10 * 60

# Bytes of randomness in a server-issued OAuth state; a state shorter than its encoding is refused.
OAUTH_STATE_BYTES = 32
OAUTH_STATE_MIN_LENGTH = 32

#: Seconds a token refresh claim lasts if its holder dies before releasing it.
TOKEN_REFRESH_CLAIM_TTL_SECONDS = 60

#: Lifetime of a queued sync's claim and state: longer than any sync takes, shorter than a stuck claim should block.
SYNC_TTL_SECONDS = 30 * 60

#: Longest activity range one request may ask for; each activity is several Strava calls, so a longer history
#: is fetched in several requests.
MAX_ACTIVITIES_RANGE_DAYS = 366

# Activities an unlink deletes per transaction, so a large account never holds every row lock at once.
UNLINK_DELETE_BATCH_SIZE = 500

#: Account links the in-process pool may hold, running or queued; each is one Strava round trip.
MAX_CONCURRENT_LINKS = 4

#: Syncs the in-process pool may hold, running or queued, when durable jobs are off.
MAX_PENDING_LOCAL_SYNCS = 50

#: Event source recorded on a queued sync.
SYNC_SOURCE_API = "api:strava_sync"


class SyncKind(StrEnum):
    """What a queued Strava sync does."""

    LINK = "link"
    GEAR = "gear"
    UNLINK = "unlink"


#: Where a queued sync is; shared by every provider's sync state.
SyncStatus = core_attempt_state.SyncStatus
