"""SQLAlchemy ORM model for health weight records."""

import uuid
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

import core.sync as core_sync
from core.database import Base


class HealthWeight(core_sync.UpdatedAtMixin, Base):
    """User health weight and body composition data.

    Attributes:
        id: Primary key, a random UUID.
        user_id: Foreign key to users table.
        date: Calendar date of the measurement.
        weight_kg: Weight in kilograms.
        bmi: Body Mass Index.
        body_fat_percent: Body fat percentage.
        body_water_percent: Body hydration percentage.
        bone_mass_kg: Bone mass in kilograms.
        muscle_mass_kg: Muscle mass in kilograms.
        physique_rating: Physique rating score.
        visceral_fat: Visceral fat rating.
        metabolic_age: Calculated metabolic age.
        source: Data source.
    """

    __tablename__ = "health_weight"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_health_weight_user_date"),
        Index("ix_health_weight_user_updated_at_id", "user_id", "updated_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the health_weight belongs",
    )
    date: Mapped[date_type] = mapped_column(
        nullable=False,
        index=True,
        comment="Health weight date (date)",
    )
    weight_kg: Mapped[Decimal] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=False,
        comment="Weight in kg",
    )
    bmi: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=True,
        comment="Body mass index (BMI)",
    )
    body_fat_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=True,
        comment="Body fat percentage",
    )
    body_water_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=True,
        comment="Body hydration percentage",
    )
    bone_mass_kg: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=True,
        comment="Bone mass in kg",
    )
    muscle_mass_kg: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=True,
        comment="Muscle mass in kg",
    )
    physique_rating: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Physique rating",
    )
    visceral_fat: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=True,
        comment="Visceral fat rating",
    )
    metabolic_age: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Metabolic age",
    )
    source: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        server_default="manual",
        default="manual",
        comment="Source of the health weight data",
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
