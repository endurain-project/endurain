"""Garmin Connect constants and closed vocabularies."""

from enum import StrEnum

PROVIDER_NAME = "garminconnect"

# A login waits this long for the user's MFA code. The stores' lifetimes must exceed it so a live
# attempt never expires under the poller.
MFA_WAIT_SECONDS = 60

# Lifetime of a link attempt's claim and state: the MFA wait plus a login that is slow to answer.
LINK_TTL_SECONDS = MFA_WAIT_SECONDS + 240

# Lifetime of a queued sync's claim and state: longer than any sync takes, shorter than a stuck
# claim should block the user.
SYNC_TTL_SECONDS = 30 * 60

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


class SyncKind(StrEnum):
    """What a queued Garmin Connect sync pulls."""

    GEAR = "gear"
    HEALTH = "health"


class SyncStatus(StrEnum):
    """Where a queued Garmin Connect sync is."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


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
