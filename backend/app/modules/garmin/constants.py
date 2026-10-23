"""Garmin Connect constants and closed vocabularies."""

from enum import StrEnum

PROVIDER_NAME = "garminconnect"

# A login waits this long for the user's MFA code. The stores' lifetimes must exceed it so a live
# attempt never expires under the poller.
MFA_WAIT_SECONDS = 60

# Longest health range one request may ask for: each day is a Garmin round trip.
MAX_HEALTH_RANGE_DAYS = 31


class SyncKind(StrEnum):
    """What a queued Garmin Connect sync pulls."""

    GEAR = "gear"
    HEALTH = "health"


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
