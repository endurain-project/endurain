"""Gear database models."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

import core.sync as core_sync
from core.database import Base


class Gear(core_sync.UpdatedAtMixin, Base):
    """Gear data model.

    Attributes:
        id: Primary key, a random UUID.
        brand: Gear brand name.
        model: Gear model name.
        nickname: Gear nickname.
        gear_type: Gear type identifier.
        user_id: Foreign key to users table.
        acquired_on: Date the user acquired the gear.
        active: Whether the gear is active.
        initial_distance: Distance the gear had before it was tracked, in meters.
        purchase_value: Gear purchase value.
        strava_gear_id: Strava gear ID.
        garminconnect_gear_id: Garmin gear ID.
        version: Optimistic-concurrency counter.
        updated_at: When the gear last changed.
    """

    __tablename__ = "gear"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
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
    acquired_on: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        default=func.current_date(),
        server_default=func.current_date(),
        comment="Date the user acquired the gear (today when not given)",
    )
    active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        comment=("Whether the gear is active (true - yes, false - no)"),
    )
    initial_distance: Mapped[Decimal] = mapped_column(
        Numeric(precision=14, scale=2),
        nullable=False,
        default=0,
        comment=("Distance of the gear before it was tracked, in meters"),
    )
    purchase_value: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=11, scale=2),
        nullable=True,
        comment="Gear purchase value",
    )
    strava_gear_id: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Strava gear ID",
    )
    garminconnect_gear_id: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Garmin Connect gear ID",
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

    # A provider gear ID is unique per user, never across users.
    __table_args__ = (
        UniqueConstraint("user_id", "strava_gear_id", name="uq_gear_user_strava_gear_id"),
        UniqueConstraint("user_id", "garminconnect_gear_id", name="uq_gear_user_garminconnect_gear_id"),
        Index("ix_gear_user_id_updated_at_id", "user_id", "updated_at", "id"),
    )


#: One nickname per user, compared case-insensitively like the nickname lookup.
Index("uq_gear_user_nickname", Gear.user_id, func.lower(Gear.nickname), unique=True)


class GearDeletion(core_sync.TombstoneMixin, Base):
    """Tombstone of a deleted gear, read by incremental sync.

    Attributes:
        id: Primary key, a random UUID.
        user_id: Owner of the deleted gear.
        record_id: The id the gear had.
        deleted_at: When the gear was deleted.
    """

    __tablename__ = "gear_deletions"

    __table_args__ = (Index("ix_gear_deletions_user_id_deleted_at_id", "user_id", "deleted_at", "id"),)

    record_id: Mapped[uuid.UUID] = mapped_column(nullable=False, comment="The id the deleted record had")
