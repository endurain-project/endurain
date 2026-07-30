"""Pydantic response schemas for the durable-jobs admin dashboard."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class JobSubscriberStats(BaseModel):
    """
    Per-subscriber job counts by status within the window.

    Attributes:
        subscriber_id: The durable subscriber.
        event_type: The event channel it reacts to.
        total: Total jobs for this subscriber in the window.
        pending: Count waiting to be claimed (includes backoff).
        claimed: Count currently leased by a worker.
        completed: Count that finished successfully.
        dead_letter: Count that exhausted retries.
    """

    subscriber_id: str
    event_type: str
    total: int
    pending: int
    claimed: int
    completed: int
    dead_letter: int


class DeadLetterJob(BaseModel):
    """
    A dead-lettered job, shown for inspection and replay.

    Attributes:
        id: The job id (used to replay it).
        event_id: The originating envelope event_id.
        event_type: The event channel.
        subscriber_id: The subscriber that failed.
        source: Where the originating event came from.
        attempts: Attempts made before dead-lettering.
        max_attempts: The attempt ceiling that was reached.
        last_error: The final failure reason.
        created_at: When the job was enqueued.
        updated_at: When the job was dead-lettered.
        completed_at: When the job reached its terminal state.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    event_type: str
    subscriber_id: str
    source: str
    attempts: int
    max_attempts: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class JobsSummary(BaseModel):
    """
    The durable-jobs admin-dashboard payload.

    Attributes:
        window_hours: The look-back window applied to the counts.
        total_jobs: Total jobs enqueued within the window.
        pending: Window count waiting to be claimed.
        claimed: Window count currently leased.
        completed: Window count finished successfully.
        dead_letter: Window count that exhausted retries.
        oldest_pending_seconds: Age of the oldest unfinished job, in seconds.
        by_subscriber: Per-subscriber breakdown within the window.
        recent_dead_letter: The current dead-letter queue contents (most recent first).
    """

    window_hours: int
    total_jobs: int
    pending: int
    claimed: int
    completed: int
    dead_letter: int
    oldest_pending_seconds: float | None
    by_subscriber: list[JobSubscriberStats]
    recent_dead_letter: list[DeadLetterJob]


class JobReplayResult(BaseModel):
    """
    The outcome of replaying a dead-lettered job.

    Attributes:
        replayed: True when the job was requeued for a fresh run.
    """

    replayed: bool
