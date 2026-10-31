"""SQLAlchemy models for health fasting tracking.

This module defines the database models for storing user fasting sessions,
including timing, duration, type, and status information.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class HealthFasting(Base):
    """User fasting session tracking data.

    Attributes:
        id: Primary key.
        user_id: Foreign key to users table.
        fast_start_time: Start time of fast.
        fast_end_time: End time of fast (null if ongoing).
        target_duration_seconds: User's target fasting duration.
        actual_duration_seconds: Calculated duration when completed.
        fasting_type: Type of fasting protocol.
        status: Current status of the fasting session.
        notes: Optional notes about the fasting session.
        source: Data source for the record.
    """

    __tablename__ = "health_fasting"
    __table_args__ = (
        Index(
            "uq_health_fasting_one_in_progress_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'in_progress'"),
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
        comment="User ID that the health_fasting belongs",
    )
    fast_start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Start time of fast",
    )
    fast_end_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="End time of fast (null if ongoing)",
    )
    target_duration_seconds: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Target fasting duration in seconds",
    )
    actual_duration_seconds: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Actual fasting duration in seconds",
    )
    fasting_type: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Type of fasting protocol (16:8, 18:6, etc.)",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="in_progress",
        comment="Status: in_progress, completed, broken, cancelled",
    )
    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Optional notes about the fasting session",
    )
    source: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Data source (manual, garmin, etc.)",
    )

    version: Mapped[int] = mapped_column(
        nullable=False,
        server_default="1",
        default=1,
        comment="Optimistic-concurrency counter, surfaced to clients as the ETag",
    )

    # SQLAlchemy bumps ``version`` on each ORM flush and adds it to the UPDATE's
    # WHERE clause, raising StaleDataError when the row moved underneath.
    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012
