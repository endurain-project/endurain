"""Event observability model — the ``event_log`` lifecycle table."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base


class EventLog(Base):
    """
    One row per event, recording its full processing lifecycle.

    Written exclusively by the event bus (never by domain handlers) so the
    system leaves a queryable trail: what was published, whether it was
    processed, by which worker, how long it took, and why it failed.

    Attributes:
        id: The envelope ``event_id`` (UUIDv4 string); stable across retries
            so it also serves as the deduplication key.
        event_type: The domain-event channel, e.g. ``activity.created``.
        event_source: Where the event originated, e.g. ``api:store_activity``.
        event_payload: The domain payload, passed through untouched.
        event_metadata: Correlation context (request_id, user_id, activity_id).
        status: Lifecycle state — published, processing, completed, failed, or
            dead_letter for bus-delivered events; queued (terminal) for events
            handed to the durable job queue.
        handler_name: The subscriber(s) that processed the event.
        worker_id: The process/consumer that handled the event.
        error_message: The failure reason when status is failed/dead_letter.
        retry_count: Processing attempts so far; 0 on first publish.
        processing_time_ms: Handler execution time in milliseconds.
        created_at: When the event was published.
        processed_at: When a consumer picked the event up.
        completed_at: When processing finished (success or failure).
    """

    __tablename__ = "event_log"
    __table_args__ = (
        Index("idx_event_log_type_status", "event_type", "status"),
        Index("idx_event_log_created", "created_at"),
        # A GIN index on event_metadata (jsonb_path_ops) is created in the
        # Alembic migration for ``@>`` correlation queries; it is Postgres-only
        # so it is intentionally not declared here (SQLite create_all in tests
        # cannot build a GIN index).
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        comment="Envelope event_id (UUIDv4); stable across retries",
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Domain-event channel, e.g. activity.created",
    )
    event_source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Where the event originated, e.g. api:store_activity",
    )
    event_payload: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        comment="Domain payload, passed through untouched",
    )
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
        comment="Correlation context (request_id, user_id, activity_id)",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="published",
        server_default="published",
        comment="published | queued | processing | completed | failed | dead_letter",
    )
    handler_name: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Subscriber(s) that processed the event, comma-separated",
    )
    worker_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Process/consumer that handled the event",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Failure reason when status is failed/dead_letter",
    )
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Processing attempts so far; 0 on first publish",
    )
    processing_time_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Handler execution time in milliseconds",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the event was published",
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When a consumer picked the event up",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When processing finished (success or failure)",
    )
