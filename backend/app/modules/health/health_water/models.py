"""
SQLAlchemy models for health water intake tracking.

This module defines the database models for storing user daily
water intake data, including consumption amount and data source.
"""

from datetime import date as date_type
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.users.users.models import Users


class HealthWater(Base):
    """
    User daily water intake tracking data.

    Attributes:
        id: Primary key, auto-incremented unique identifier.
        user_id: Foreign key referencing users.id.
        date: Calendar date for the water intake record.
        amount_ml: Total water consumed in milliliters.
        source: Source of the water intake data.
        user: Relationship to the Users model.

    Table:
        health_water

    Relationships:
        - Many-to-One with Users model through user_id
    """

    __tablename__ = "health_water"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the health_water belongs",
    )
    date: Mapped[date_type] = mapped_column(
        nullable=False,
        index=True,
        comment="Health water intake date (date)",
    )
    amount_ml: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=False,
        comment="Water consumed in milliliters",
    )
    source: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Source of the health water data",
    )

    # Define a relationship to the Users model
    users: Mapped["Users"] = relationship(back_populates="health_water")
