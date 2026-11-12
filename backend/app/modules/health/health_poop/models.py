"""SQLAlchemy models for health poop (bowel movement) tracking.

This module defines the database models for storing user bowel
movement data, including Bristol stool scale type, color, and
optional notes.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

import core.sync as core_sync
from core.database import Base


class HealthPoop(core_sync.UpdatedAtMixin, Base):
    """User bowel movement tracking data.

    Attributes:
        id: Primary key, a random UUID.
        user_id: Foreign key referencing users.id.
        date_time: Date and time of the bowel movement.
        bristol_type: Bristol Stool Scale type (1-7).
        color: Stool color description.
        notes: Optional notes about the bowel movement.
        source: Source of the data.

    Table:
        health_poop
    """

    __tablename__ = "health_poop"
    __table_args__ = (Index("ix_health_poop_user_updated_at_id", "user_id", "updated_at", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the health_poop belongs",
    )
    date_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Date and time of bowel movement",
    )
    bristol_type: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Bristol Stool Scale type (1-7)",
    )
    color: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Stool color description",
    )
    notes: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Optional notes about the bowel movement",
    )
    source: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        server_default="manual",
        default="manual",
        comment="Source of the health poop data",
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
