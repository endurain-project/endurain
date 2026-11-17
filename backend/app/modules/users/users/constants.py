"""Domain constants for users."""

import uuid
from enum import StrEnum

import core.job_status as core_job_status

#: Domain-owned storage namespace for profile photos. For the ``local`` backend this maps to
#: ``{DATA_DIR}/user_images`` — the directory the photos already live in — so an existing
#: install needs no data migration; for S3 it is the object key prefix.
USER_IMAGE_STORAGE_AREA = "user_images"


def photo_key(user_id: uuid.UUID, extension: str) -> str:
    """Return the storage key of a user's profile photo.

    Args:
        user_id: The user the photo belongs to.
        extension: The image file extension, with its leading dot.

    Returns:
        The key in the photo area.
    """
    return f"{user_id}{extension}"


#: Fields a user may change on their own account through the self-service profile endpoint.
#: Any field not in this set is dropped before persistence, so a payload cannot escalate
#: privilege through mass assignment (for example setting ``access_type`` to ``admin``).
PROFILE_SELF_SERVICE_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "city",
        "birthdate",
        "preferred_language",
        "gender",
        "units",
        "weight_units",
        "height",
        "max_heart_rate",
        "first_day_of_week",
        "currency",
        "timezone",
    }
)

#: Longest edge, in pixels, a stored profile photo is reduced to.
USER_IMAGE_MAX_DIMENSION = 512


#: Lifetime of a queued deletion's claim and state: longer than any deletion takes, shorter than a stuck claim
#: should block an administrator from queueing it again.
DELETION_STATE_TTL_SECONDS = 2 * 60 * 60

#: Activities erased per transaction by an account deletion. Each carries streams, laps and media rows through
#: the database cascade, so a batch is small enough to hold its row locks briefly.
DELETION_BATCH_SIZE = 100

#: Shortest time budget of one durable deletion pass, in seconds. The budget is a fraction of the job lease, so
#: a pass is never mistaken for a dead worker.
DELETION_PASS_MIN_SECONDS = 30

#: A durable deletion pass lasts at most this fraction of the job lease.
DELETION_PASS_LEASE_FRACTION = 3

#: Seconds an administrator waits before polling an account deletion, which erases data in batches.
DELETION_POLL_SECONDS = 10

#: Deletions the in-process pool runs at once when no durable worker does.
DELETION_POOL_WORKERS = 1

#: Deletions the in-process pool holds, running and queued, before a new request is refused.
DELETION_POOL_MAX_PENDING = 5

#: How often the sweep looks for deletions that never finished, in minutes.
DELETION_SWEEP_INTERVAL_MINUTES = 60

#: How often the photo area is swept for blobs no user names.
PHOTO_SWEEP_INTERVAL_MINUTES = 1440

#: A deletion queued longer ago than this and still not finished is stalled: it outlasts the claim, so no
#: live job holds it.
DELETION_STALL_AFTER_SECONDS = DELETION_STATE_TTL_SECONDS + 60 * 60

#: Times the sweep queues one account's deletion again before it leaves the account for an administrator.
DELETION_SWEEP_MAX_ATTEMPTS = 5

#: Stalled deletions one sweep query reads.
DELETION_SWEEP_BATCH_SIZE = 100

#: Who asked for the deletion, as recorded on the event.
DELETION_SOURCE_API = "api:delete_user"

#: Who asked for a deletion the sweep queued again, as recorded on the event.
DELETION_SOURCE_SWEEP = "scheduler:users_deletion_sweep"


#: The job kind of a queued account deletion.
DELETION_JOB = "user_deletion"

#: Where a queued deletion is; shared by every queued job's state.
DeletionStatus = core_job_status.JobState


class DeletionKind(StrEnum):
    """What a queued deletion state tracks; one, but the shared sync state is keyed by kind."""

    ACCOUNT = "account"
