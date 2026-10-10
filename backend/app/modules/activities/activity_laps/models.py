"""Activity laps ORM models."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DECIMAL, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class ActivityLaps(Base):
    """ORM model representing a single lap within an activity."""

    __tablename__ = "activity_laps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Activity ID that the activity lap belongs",
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Lap start date (DATETIME)",
    )
    start_position_lat: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap start position latitude",
    )
    start_position_long: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap start position longitude",
    )
    end_position_lat: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap end position latitude",
    )
    end_position_long: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap end position longitude",
    )
    total_elapsed_time: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap total elapsed time (s)",
    )
    total_timer_time: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap total timer time (s)",
    )
    total_distance: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap total distance (m)",
    )
    total_cycles: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Lap total cycles",
    )
    total_calories: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Lap total calories",
    )
    avg_heart_rate: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Lap average heart rate",
    )
    max_heart_rate: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Lap maximum heart rate",
    )
    avg_cadence: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Lap average cadence",
    )
    max_cadence: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Lap maximum cadence",
    )
    avg_power: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Lap average power",
    )
    max_power: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Lap maximum power",
    )
    total_ascent: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Lap total ascent (m)",
    )
    total_descent: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Lap total descent (m)",
    )
    intensity: Mapped[str | None] = mapped_column(
        String(length=250),
        nullable=True,
        comment="Lap intensity",
    )
    lap_trigger: Mapped[str | None] = mapped_column(
        String(length=250),
        nullable=True,
        comment="Lap trigger",
    )
    sport: Mapped[str | None] = mapped_column(
        String(length=250),
        nullable=True,
        comment="Lap sport",
    )
    sub_sport: Mapped[str | None] = mapped_column(
        String(length=250),
        nullable=True,
        comment="Lap sub sport",
    )
    normalized_power: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Lap normalized power",
    )
    total_work: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Lap total work",
    )
    avg_vertical_oscillation: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap average vertical oscillation",
    )
    avg_stance_time: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap average stance time",
    )
    avg_fractional_cadence: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap average fractional cadence",
    )
    max_fractional_cadence: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap maximum fractional cadence",
    )
    enhanced_avg_pace: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap enhanced average pace",
    )
    enhanced_avg_speed: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap enhanced average speed",
    )
    enhanced_max_pace: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap enhanced maximum pace",
    )
    enhanced_max_speed: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap enhanced maximum speed",
    )
    enhanced_min_altitude: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap enhanced minimum altitude",
    )
    enhanced_max_altitude: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap enhanced maximum altitude",
    )
    avg_vertical_ratio: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap average vertical ratio",
    )
    avg_step_length: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap average step length",
    )
