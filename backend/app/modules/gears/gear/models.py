"""Gear database models."""

from datetime import datetime as datetime_type
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base


class Gear(Base):
    """Gear data model.

    Attributes:
        id: Primary key.
        brand: Gear brand name.
        model: Gear model name.
        nickname: Gear nickname.
        gear_type: Gear type identifier.
        user_id: Foreign key to users table.
        created_at: Gear creation timestamp.
        active: Whether the gear is active.
        initial_kms: Initial kilometers.
        purchase_value: Gear purchase value.
        strava_gear_id: Strava gear ID.
        garminconnect_gear_id: Garmin gear ID.
    """

    __tablename__ = "gear"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    brand: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Gear brand (May include spaces)",
    )
    model: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Gear model (May include spaces)",
    )
    nickname: Mapped[str] = mapped_column(
        String(250),
        index=True,
        nullable=False,
        comment=("Gear nickname (May include spaces)"),
    )
    gear_type: Mapped[int] = mapped_column(
        nullable=False,
        comment=(
            "Gear type (1 - bike, 2 - shoes,"
            " 3 - wetsuit, 4 - racquet,"
            " 5 - skis, 6 - snowboard,"
            " 7 - windsurf,"
            " 8 - water sports board)"
        ),
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment=("User ID that the gear belongs to"),
    )
    created_at: Mapped[datetime_type] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        comment="Gear creation date (DateTime)",
    )
    active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        comment=("Whether the gear is active (true - yes, false - no)"),
    )
    initial_kms: Mapped[Decimal] = mapped_column(
        Numeric(precision=11, scale=2),
        nullable=False,
        default=0,
        comment=("Initial kilometers of the gear"),
    )
    purchase_value: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=11, scale=2),
        nullable=True,
        comment="Gear purchase value",
    )
    strava_gear_id: Mapped[str | None] = mapped_column(
        String(45),
        unique=True,
        nullable=True,
        comment="Strava gear ID",
    )
    garminconnect_gear_id: Mapped[str | None] = mapped_column(
        String(45),
        unique=True,
        nullable=True,
        comment="Garmin Connect gear ID",
    )
