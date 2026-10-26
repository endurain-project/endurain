"""Strava constants and closed vocabularies."""

from enum import StrEnum

PROVIDER_NAME = "strava"

#: The name the Strava export layout registers under with bulk import.
BULK_IMPORT_FORMAT_NAME = "strava"

#: Seconds a request to Strava may take before it is abandoned; stravalib sets no timeout of its own.
HTTP_TIMEOUT_SECONDS = 30

#: Seconds the user has to finish the Strava consent screen before the one-time state expires.
OAUTH_STATE_TTL_SECONDS = 10 * 60

#: Seconds a token refresh claim lasts if its holder dies before releasing it.
TOKEN_REFRESH_CLAIM_TTL_SECONDS = 60

#: Lifetime of a queued sync's claim and state: longer than any sync takes, shorter than a stuck claim should block.
SYNC_TTL_SECONDS = 30 * 60

#: Syncs the in-process pool may hold, running or queued, when durable jobs are off.
MAX_PENDING_LOCAL_SYNCS = 50

#: Event source recorded on a queued sync.
SYNC_SOURCE_API = "api:strava_sync"


class SyncKind(StrEnum):
    """What a queued Strava sync does."""

    GEAR = "gear"
    UNLINK = "unlink"


class SyncStatus(StrEnum):
    """Where a queued Strava sync is."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
