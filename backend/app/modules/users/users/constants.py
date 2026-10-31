"""Domain constants for users."""

from enum import StrEnum

import core.attempt_state as core_attempt_state

#: Domain-owned storage namespace for profile photos. For the ``local`` backend this maps to
#: ``{DATA_DIR}/user_images`` — the directory the photos already live in — so an existing
#: install needs no data migration; for S3 it is the object key prefix.
USER_IMAGE_STORAGE_AREA = "user_images"

#: Fields a user may change on their own account through the self-service profile endpoint.
#: Any field not in this set is dropped before persistence, so a payload cannot escalate
#: privilege through mass assignment (for example setting ``access_type`` to ``admin``).
PROFILE_SELF_SERVICE_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "username",
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

#: Photo extensions accepted on upload.
ALLOWED_USER_IMAGE_EXTENSIONS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".webp"})


#: Lifetime of a queued deletion's claim and state: longer than any deletion takes, shorter than a stuck claim
#: should block an administrator from queueing it again.
DELETION_STATE_TTL_SECONDS = 2 * 60 * 60

#: Activities erased per transaction by an account deletion. Each carries streams, laps and media rows through
#: the database cascade, so a batch is small enough to hold its row locks briefly.
DELETION_BATCH_SIZE = 100

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


#: Where a queued deletion is; shared by every queued job's state.
DeletionStatus = core_attempt_state.SyncStatus


class DeletionKind(StrEnum):
    """What a queued deletion state tracks; one, but the shared sync state is keyed by kind."""

    ACCOUNT = "account"
