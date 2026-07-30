"""SQLAlchemy ORM model for user-facing activity ingestion jobs."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base


class ActivityIngestionJob(Base):
    """One row per user-initiated import, tracked until it finishes.

    The *user-facing* half of an ingestion request: an uploaded file, or a
    provider refresh. Both return a job id immediately and do the work on a
    background worker, so the client polls this row instead of holding a request
    open for a parse or a provider round-trip.

    One table rather than one per kind because the caller's question is the same
    either way — did it finish, what did it create, why did it fail. Only how the
    activities are obtained differs, and that is what ``kind`` records.

    It deliberately does not reuse ``processing_jobs``: that table is the generic
    execution substrate (leases, attempts, backoff, ``last_error`` holding raw
    exception text) and is admin-only for good reason. This table is scoped to a
    user, carries only a sanitized error code, and survives the choice of
    executor — the contract is identical whether the work ran on the durable
    worker or on the in-process fallback.

    Attributes:
        id: Job identifier (UUIDv4 string), returned to the client.
        user_id: Owner of the request; every read is filtered by it.
        kind: ``upload`` or ``refresh``.
        filename: Original client-supplied filename for an upload, kept for
            display only and never used to build a filesystem path. Null for a
            refresh.
        staged_key: Storage key of the uploaded blob awaiting parsing, cleared
            once consumed. Null for a refresh.
        status: Lifecycle state: pending, processing, completed, or failed.
        error_code: Stable, sanitized reason when ``status`` is failed.
        activity_ids: Ids created by the import, so the client can refresh
            exactly what changed instead of invalidating the whole feed.
        created_at: When the request was accepted.
        updated_at: When the job last changed state.
        completed_at: When the job reached a terminal state (completed/failed).
    """

    __tablename__ = "activity_ingestion_jobs"
    __table_args__ = (Index("idx_activity_ingestion_jobs_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        comment="Ingestion job identifier (UUIDv4 string)",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User that owns the ingestion request",
    )
    kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="upload",
        server_default="upload",
        comment="upload | refresh",
    )
    filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Original client filename for an upload, for display only",
    )
    staged_key: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Storage key of the staged upload; cleared once consumed",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        comment="pending | processing | completed | failed",
    )
    error_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Sanitized failure reason when status is failed",
    )
    activity_ids: Mapped[list[Any] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
        comment="Ids of the activities the import created",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the request was accepted",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When the job last changed state",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the job reached a terminal state (completed/failed)",
    )
