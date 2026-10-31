"""Constants of the bulk activity edit job."""

from enum import StrEnum

import core.attempt_state as core_attempt_state

#: Where a queued bulk edit is; shared by every queued job's state.
BulkEditStatus = core_attempt_state.SyncStatus


class BulkEditKind(StrEnum):
    """What a queued bulk edit changes; one today, but the shared sync state is keyed by kind."""

    VISIBILITY = "visibility"


#: Lifetime of a queued bulk edit's claim and state: longer than any edit takes, so a stuck claim does not
#: block the user from queueing another for long.
BULK_EDIT_STATE_TTL_SECONDS = 60 * 60

#: Activities changed per transaction by a bulk edit, so a batch holds its row locks briefly.
BULK_EDIT_BATCH_SIZE = 500

#: Bulk edits the in-process pool runs at once when no durable worker does.
BULK_EDIT_POOL_WORKERS = 1

#: Bulk edits the in-process pool holds, running and queued, before a new request is refused.
BULK_EDIT_POOL_MAX_PENDING = 5

#: Who asked for the edit, as recorded on the events it publishes.
BULK_EDIT_SOURCE = "job:bulk_edit_activities"
