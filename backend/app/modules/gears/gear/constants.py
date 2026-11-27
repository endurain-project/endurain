"""Domain constants for gear."""

#: Name of the gear section in a profile archive (``data/gears.json``), also the key of its restored ids.
PROFILE_ARCHIVE_KEY = "gears"

#: The job kind of a gear deletion, as ``GET /jobs/{job_id}`` and the realtime hints name it.
DELETION_JOB = "gear_deletion"

#: Seconds a client waits before polling a gear deletion, which can unassign a gear from a whole library.
DELETION_POLL_SECONDS = 2

#: Lifetime of a queued deletion's claim and state: longer than any deletion takes, so a stuck claim does not
#: block the user from deleting the gear again for long.
DELETION_STATE_TTL_SECONDS = 60 * 60

#: Activities a deletion unassigns the gear from per transaction, so a batch holds its row locks briefly.
DELETION_BATCH_SIZE = 500

#: Deletions the in-process pool runs at once when no durable worker does.
DELETION_POOL_WORKERS = 1

#: Deletions the in-process pool holds, running and queued, before a new request is refused.
DELETION_POOL_MAX_PENDING = 5

#: Who asked for the deletion, as recorded on the events it publishes.
DELETION_SOURCE = "job:delete_gear"
