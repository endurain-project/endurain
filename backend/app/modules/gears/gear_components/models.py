"""Gear components database models."""

from datetime import datetime as datetime_type
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)
from sqlalchemy.sql import func

from core.database import Base

if TYPE_CHECKING:
    from modules.gears.gear.models import Gear
    from modules.users.users.models import Users


class GearComponents(Base):
    """
    Gear component data model.

    Attributes:
        id: Primary key.
        user_id: Foreign key to users table.
        gear_id: Foreign key to gear table.
        type: Type of gear component.
        brand: Gear component brand.
        model: Gear component model.
        purchase_date: Purchase date.
        retired_date: Retired date.
        active: Whether component is active.
        expected_kms: Expected kilometers.
        purchase_value: Purchase value.
        users: Relationship to Users model.
        gear: Relationship to Gear model.
    """

    __tablename__ = "gear_components"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment=("User ID that the gear component belongs to"),
    )
    gear_id: Mapped[int] = mapped_column(
        ForeignKey("gear.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment=("Gear ID associated with this component"),
    )
    type: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        comment="Type of gear component",
    )
    brand: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        comment=("Gear component brand (May include spaces)"),
    )
    model: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        comment=("Gear component model (May include spaces)"),
    )
    purchase_date: Mapped[datetime_type] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        comment=("Gear component purchase date (DateTime)"),
    )
    retired_date: Mapped[datetime_type | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment=("Gear component retired date (DateTime)"),
    )
    active: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment=("Whether the gear component is active (true - yes, false - no)"),
    )
    expected_kms: Mapped[int | None] = mapped_column(
        nullable=True,
        comment=("Expected kilometers of the gear component"),
    )
    purchase_value: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=11, scale=2),
        nullable=True,
        comment=("Purchase value of the gear component"),
    )

    users: Mapped["Users"] = relationship(
        back_populates="gear_components",
    )
    gear: Mapped["Gear"] = relationship(
        back_populates="gear_components",
    )
