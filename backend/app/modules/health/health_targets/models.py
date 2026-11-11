"""SQLAlchemy ORM model for per-user health targets."""

from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column

import core.sync as core_sync
from core.database import Base


class HealthTargets(core_sync.UpdatedAtMixin, Base):
    """User health targets configuration.

    Attributes:
        id: Primary key.
        user_id: Foreign key to users table (unique).
        weight_kg: Target weight in kg.
        steps: Target daily steps count.
        sleep_seconds: Target sleep duration in seconds.
        fasting_seconds: Target fasting duration in seconds.
        water_ml: Target daily water intake in milliliters.
        poop_count: Target daily bowel movement count.
    """

    __tablename__ = "health_targets"
    __table_args__ = (Index("ix_health_targets_user_updated_at_id", "user_id", "updated_at", "id"),)

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="User ID that the health_target belongs",
    )
    weight_kg: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=True,
        comment="Weight in kg",
    )
    steps: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Number of steps taken",
    )
    sleep_seconds: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Target sleep duration in seconds",
    )
    fasting_seconds: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Target fasting duration in seconds",
    )
    water_ml: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=True,
        comment="Target daily water intake in milliliters",
    )
    poop_count: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Target daily bowel movement count",
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
