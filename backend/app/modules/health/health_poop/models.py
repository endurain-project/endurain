"""
SQLAlchemy models for health poop (bowel movement) tracking.

This module defines the database models for storing user bowel
movement data, including Bristol stool scale type, color, and
optional notes.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.users.users.models import Users


class HealthPoop(Base):
    """
    User bowel movement tracking data.

    Attributes:
        id: Primary key, auto-incremented unique identifier.
        user_id: Foreign key referencing users.id.
        date_time: Date and time of the bowel movement.
        bristol_type: Bristol Stool Scale type (1-7).
        color: Stool color description.
        notes: Optional notes about the bowel movement.
        source: Source of the data.
        user: Relationship to the Users model.

    Table:
        health_poop

    Relationships:
        - Many-to-One with Users model through user_id
    """

    __tablename__ = "health_poop"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
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
    source: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Source of the health poop data",
    )

    # Define a relationship to the Users model
    users: Mapped["Users"] = relationship(back_populates="health_poop")
