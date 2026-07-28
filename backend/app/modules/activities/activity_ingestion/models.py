"""SQLAlchemy ORM model for user-facing activity upload jobs."""

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


class ActivityUploadJob(Base):
    """
    One row per uploaded activity file, tracking it until the import finishes.

    This is the *user-facing* half of an upload. The request stages the file and
    returns this row's id; the parse then happens on a background worker, so the
    client polls this row instead of holding a request open for the duration.

    It deliberately does not reuse ``processing_jobs``: that table is the generic
    execution substrate (leases, attempts, backoff, ``last_error`` holding raw
    exception text) and is admin-only for good reason. This table is scoped to a
    user, carries only a sanitized error code, and survives the choice of
    executor — the contract is identical whether the work ran on the durable
    worker or on the in-process fallback.

    Attributes:
        id: Job identifier (UUIDv4 string), returned to the client.
        user_id: Owner of the upload; every read is filtered by it.
        filename: Original client-supplied filename, kept for display only and
            never used to build a filesystem path.
        staged_path: Absolute path of the server-named file awaiting parsing,
            cleared once the file has been consumed.
        status: Lifecycle state: pending, processing, completed, or failed.
        error_code: Stable, sanitized reason when ``status`` is failed.
        activity_ids: Ids created by the import, so the client can refresh
            exactly what changed instead of invalidating the whole feed.
        created_at: When the upload was accepted.
        updated_at: When the job last changed state.
        completed_at: When the job reached a terminal state (completed/failed).
    """

    __tablename__ = "activity_upload_jobs"
    __table_args__ = (Index("idx_activity_upload_jobs_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        comment="Upload job identifier (UUIDv4 string)",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User that owns the upload",
    )
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Original client filename, for display only",
    )
    staged_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Server-named staged file awaiting parsing; cleared once consumed",
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
        comment="When the upload was accepted",
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
