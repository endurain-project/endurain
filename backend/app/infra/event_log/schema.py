"""Pydantic response schemas for the event_log admin dashboard."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class EventTypeStats(BaseModel):
    """
    Per-event-type throughput, outcome, and latency counts.

    Attributes:
        event_type: The domain-event channel.
        total: Total events of this type in the window.
        published: Count still in the published state.
        queued: Count handed to the durable job queue (terminal in event_log;
            execution is tracked per-subscriber in the Jobs dashboard).
        processing: Count currently processing.
        completed: Count that finished successfully.
        failed: Count that failed.
        dead_letter: Count moved to dead-letter.
        avg_processing_time_ms: Mean handler time, or None when unmeasured.
        max_processing_time_ms: Slowest handler time, or None.
    """

    event_type: str
    total: int
    published: int
    queued: int
    processing: int
    completed: int
    failed: int
    dead_letter: int
    avg_processing_time_ms: float | None
    max_processing_time_ms: int | None


class EventLogPending(BaseModel):
    """
    A group of not-yet-finished events and its oldest age.

    Attributes:
        event_type: The domain-event channel.
        status: The pending state (published or processing).
        count: Number of events in this group.
        oldest_seconds: Age of the oldest event in the group, in seconds.
    """

    event_type: str
    status: str
    count: int
    oldest_seconds: float | None


class EventLogFailure(BaseModel):
    """
    A single failed or dead-lettered event for inspection.

    Attributes:
        id: The event_id.
        event_type: The domain-event channel.
        event_source: Where the event originated.
        handler_name: The subscriber(s) that processed the event.
        error_message: The failure reason.
        retry_count: Processing attempts so far.
        event_metadata: Correlation context (request_id, user_id, activity_id).
        created_at: When the event was published.
        completed_at: When processing finished.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    event_source: str
    handler_name: str | None
    error_message: str | None
    retry_count: int
    event_metadata: dict[str, Any] | None
    created_at: datetime
    completed_at: datetime | None


class EventLogSummary(BaseModel):
    """
    The full admin-dashboard payload, aggregated from event_log.

    Attributes:
        window_hours: The look-back window applied to the aggregates.
        total_events: Total events recorded within the window.
        by_type: Per-event-type throughput/outcome/latency stats.
        pending: Not-yet-finished event groups and their oldest age.
        recent_failures: The most recent failed/dead-lettered events.
    """

    window_hours: int
    total_events: int
    by_type: list[EventTypeStats]
    pending: list[EventLogPending]
    recent_failures: list[EventLogFailure]
