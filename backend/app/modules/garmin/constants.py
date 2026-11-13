"""Garmin Connect constants and closed vocabularies."""

from enum import StrEnum

import core.job_status as core_job_status

PROVIDER_NAME = "garminconnect"

#: The job kind of a link attempt.
LINK_JOB = "garmin_link"

#: Seconds a client waits before polling a Garmin Connect link attempt (a login takes a few seconds).
LINK_POLL_SECONDS = 2

#: Seconds a client waits before polling a Garmin Connect gear or health sync.
SYNC_POLL_SECONDS = 5

# A login waits this long for the user's MFA code. The stores' lifetimes must exceed it so a live
# attempt never expires under the poller.
MFA_WAIT_SECONDS = 180

# Lifetime of a link attempt's claim and state: the MFA wait plus a login that is slow to answer.
LINK_TTL_SECONDS = MFA_WAIT_SECONDS + 240

# How long a refresh waits after Garmin Connect answers 429, which reports no reset time.
RATE_LIMIT_COOLDOWN_SECONDS = 15 * 60

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


#: Where a queued sync is; shared by every provider's sync state.
SyncStatus = core_job_status.JobState


def job_name(kind: SyncKind) -> str:
    """Name the job kind of a queued sync.

    Args:
        kind: What the sync pulls.

    Returns:
        The job kind, such as ``garmin_sync_gear``.
    """
    return f"garmin_sync_{kind.value}"


class LinkFailure(StrEnum):
    """Why a Garmin Connect link attempt failed, for the client to word."""

    INVALID_CREDENTIALS = "invalid_credentials"
    INCORRECT_MFA = "incorrect_mfa"
    TOO_MANY_REQUESTS = "too_many_requests"
    INTERNAL = "internal"
