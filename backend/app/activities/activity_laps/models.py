from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    String,
    DECIMAL,
    DateTime,
)
from sqlalchemy.orm import relationship
from core.database import Base


class ActivityLaps(Base):
    __tablename__ = "activity_laps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    activity_id = Column(
        Integer,
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Activity ID that the activity lap belongs",
    )
    start_time = Column(DateTime, nullable=False, comment="Lap start date (DATETIME)")
    start_position_lat = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap start position latitude",
    )
    start_position_long = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap start position longitude",
    )
    end_position_lat = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap end position latitude",
    )
    end_position_long = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap end position longitude",
    )
    total_elapsed_time = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap total elapsed time (s)",
    )
    total_timer_time = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap total timer time (s)",
    )
    total_distance = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap total distance (m)",
    )
    total_cycles = Column(
        Integer,
        nullable=True,
        comment="Lap total cycles",
    )
    total_calories = Column(
        Integer,
        nullable=True,
        comment="Lap total calories",
    )
    avg_heart_rate = Column(
        Integer,
        nullable=True,
        comment="Lap average heart rate",
    )
    max_heart_rate = Column(
        Integer,
        nullable=True,
        comment="Lap maximum heart rate",
    )
    avg_cadence = Column(
        Integer,
        nullable=True,
        comment="Lap average cadence",
    )
    max_cadence = Column(
        Integer,
        nullable=True,
        comment="Lap maximum cadence",
    )
    avg_power = Column(
        Integer,
        nullable=True,
        comment="Lap average power",
    )
    max_power = Column(
        Integer,
        nullable=True,
        comment="Lap maximum power",
    )
    total_ascent = Column(
        Integer,
        nullable=True,
        comment="Lap total ascent (m)",
    )
    total_descent = Column(
        Integer,
        nullable=True,
        comment="Lap total descent (m)",
    )
    intensity = Column(
        String(length=250),
        nullable=True,
        comment="Lap intensity",
    )
    lap_trigger = Column(
        String(length=250),
        nullable=True,
        comment="Lap trigger",
    )
    sport = Column(
        String(length=250),
        nullable=True,
        comment="Lap sport",
    )
    sub_sport = Column(
        String(length=250),
        nullable=True,
        comment="Lap sub sport",
    )
    normalized_power = Column(
        Integer,
        nullable=True,
        comment="Lap normalized power",
    )
    total_work = Column(
        Integer,
        nullable=True,
        comment="Lap total work",
    )
    avg_vertical_oscillation = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap average vertical oscillation",
    )
    avg_stance_time = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap average stance time",
    )
    avg_fractional_cadence = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap average fractional cadence",
    )
    max_fractional_cadence = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap maximum fractional cadence",
    )
    enhanced_avg_pace = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap enhanced average pace",
    )
    enhanced_avg_speed = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap enhanced average speed",
    )
    enhanced_max_pace = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap enhanced maximum pace",
    )
    enhanced_max_speed = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap enhanced maximum speed",
    )
    enhanced_min_altitude = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap enhanced minimum altitude",
    )
    enhanced_max_altitude = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap enhanced maximum altitude",
    )
    avg_vertical_ratio = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap average vertical ratio",
    )
    avg_step_length = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Lap average step length",
    )

    # Define a relationship to the Users model
    activity = relationship("Activity", back_populates="activity_laps")
