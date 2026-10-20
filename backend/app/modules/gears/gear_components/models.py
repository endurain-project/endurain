"""Gear components database models."""

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import (
    Date,
    ForeignKey,
    Numeric,
    String,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)
from sqlalchemy.sql import func

from core.database import Base


class GearComponents(Base):
    """Gear component data model.

    Attributes:
        id: Primary key.
        user_id: Foreign key to users table.
        gear_id: Foreign key to gear table.
        type: Type of gear component.
        brand: Gear component brand.
        model: Gear component model.
        purchase_date: Purchase date (calendar date, no time of day).
        retired_date: Retired date (calendar date, no time of day).
        active: Whether component is active.
        expected_kms: Expected kilometers.
        purchase_value: Purchase value.
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
    purchase_date: Mapped[date_type] = mapped_column(
        Date(),
        nullable=False,
        default=func.current_date(),
        comment=("Gear component purchase date (Date)"),
    )
    retired_date: Mapped[date_type | None] = mapped_column(
        Date(),
        nullable=True,
        comment=("Gear component retired date (Date)"),
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
    version: Mapped[int] = mapped_column(
        nullable=False,
        server_default="1",
        default=1,
        comment="Optimistic-concurrency counter, surfaced to clients as the ETag",
    )

    # SQLAlchemy bumps ``version`` on each ORM flush and adds it to the UPDATE's
    # WHERE clause, raising StaleDataError when the row moved underneath.
    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012
