"""Notification database models."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base


class Notification(Base):
    """User notification data.

    Attributes:
        id: Primary key.
        user_id: Foreign key to users table.
        type: Notification type.
        options: Notification options (JSON).
        read: Whether the notification has been read.
        created_at: Notification creation date.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_user_id_created_at", "user_id", "created_at"),
        Index("ix_notifications_read_created_at", "created_at", postgresql_where=text("read")),
        UniqueConstraint(
            "source_event_id",
            "user_id",
            "type",
            name="uq_notifications_source_event_user_type",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User ID that the notification belongs to",
    )
    type: Mapped[int] = mapped_column(
        nullable=False,
        comment="Notification type",
    )
    source_event_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="Durable event ID used to make event-driven creation idempotent",
    )
    options: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Notification options (JSON)",
    )
    read: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment=("Has the notification been read (True) or not (False)"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        comment=("Notification creation date (DateTime)"),
    )
