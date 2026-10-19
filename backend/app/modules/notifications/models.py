"""Notification database models."""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base

if TYPE_CHECKING:
    from modules.users.users.models import Users


class Notification(Base):
    """
    User notification data.

    Attributes:
        id: Primary key.
        user_id: Foreign key to users table.
        type: Notification type.
        options: Notification options (JSON).
        read: Whether the notification has been read.
        created_at: Notification creation date.
        users: Relationship to Users model.
    """

    __tablename__ = "notifications"
    __table_args__ = (
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
        index=True,
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

    # Define a relationship to the Users model
    users: Mapped["Users"] = relationship(back_populates="notifications")
