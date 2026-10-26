"""Garmin Connect constants and closed vocabularies."""

from enum import StrEnum

import core.attempt_state as core_attempt_state

PROVIDER_NAME = "garminconnect"

# A login waits this long for the user's MFA code. The stores' lifetimes must exceed it so a live
# attempt never expires under the poller.
MFA_WAIT_SECONDS = 60

# Lifetime of a link attempt's claim and state: the MFA wait plus a login that is slow to answer.
LINK_TTL_SECONDS = MFA_WAIT_SECONDS + 240

# Lifetime of a queued sync's claim and state: longer than any sync takes, shorter than a stuck
# claim should block the user.
SYNC_TTL_SECONDS = 30 * 60

# How long a refresh waits after Garmin Connect answers 429, which reports no reset time.
RATE_LIMIT_COOLDOWN_SECONDS = 15 * 60

# Link logins one process runs at once; each holds a thread for up to the MFA wait.
MAX_CONCURRENT_LINKS = 4

# Syncs the in-process pool may hold, running or queued, when durable jobs are off.
MAX_PENDING_LOCAL_SYNCS = 50

# How long the scheduled pull waits for a pool slot before it stops: it runs on the scheduler
# thread, so it can wait for the pool to drain where a request is refused at once.
SCHEDULED_SLOT_WAIT_SECONDS = 600

# Event sources recorded on a queued sync, by who asked for it.
SYNC_SOURCE_API = "api:garmin_sync"
SYNC_SOURCE_SCHEDULER = "scheduler:garmin_health_sync"

# Longest health range one request may ask for: each day is a Garmin round trip.
MAX_HEALTH_RANGE_DAYS = 31

# Longest activity range one request may ask for; a longer history is fetched in several requests.
MAX_ACTIVITIES_RANGE_DAYS = 366


class SyncKind(StrEnum):
    """What a queued Garmin Connect sync pulls."""

    GEAR = "gear"
    HEALTH = "health"


#: Where a queued sync is; shared by every provider's sync state.
SyncStatus = core_attempt_state.SyncStatus


class LinkStatus(StrEnum):
    """Where a Garmin Connect link attempt is."""

    PENDING = "pending"
    MFA_REQUIRED = "mfa_required"
    COMPLETED = "completed"
    FAILED = "failed"


class LinkFailure(StrEnum):
    """Why a Garmin Connect link attempt failed, for the client to word."""

    INVALID_CREDENTIALS = "invalid_credentials"
    INCORRECT_MFA = "incorrect_mfa"
    TOO_MANY_REQUESTS = "too_many_requests"
    INTERNAL = "internal"
