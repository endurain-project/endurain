from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    ForeignKey,
    DECIMAL,
    JSON,
)
from sqlalchemy.orm import relationship
from core.database import Base


class HealthSleep(Base):
    __tablename__ = "health_sleep"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the health_sleep belongs",
    )
    date = Column(
        Date,
        nullable=False,
        index=True,
        comment="Calendar date of the sleep session",
    )
    sleep_start_time_gmt = Column(
        DateTime,
        nullable=True,
        comment="Start time of sleep in GMT",
    )
    sleep_end_time_gmt = Column(
        DateTime,
        nullable=True,
        comment="End time of sleep in GMT",
    )
    sleep_start_time_local = Column(
        DateTime,
        nullable=True,
        comment="Start time of sleep in local time",
    )
    sleep_end_time_local = Column(
        DateTime,
        nullable=True,
        comment="End time of sleep in local time",
    )
    total_sleep_seconds = Column(
        Integer,
        nullable=True,
        comment="Total duration of sleep in seconds",
    )
    nap_time_seconds = Column(
        Integer,
        nullable=True,
        comment="Duration of naps in seconds",
    )
    unmeasurable_sleep_seconds = Column(
        Integer,
        nullable=True,
        comment="Unmeasurable sleep duration in seconds",
    )
    deep_sleep_seconds = Column(
        Integer,
        nullable=True,
        comment="Duration of deep sleep in seconds",
    )
    light_sleep_seconds = Column(
        Integer,
        nullable=True,
        comment="Duration of light sleep in seconds",
    )
    rem_sleep_seconds = Column(
        Integer,
        nullable=True,
        comment="Duration of REM sleep in seconds",
    )
    awake_sleep_seconds = Column(
        Integer,
        nullable=True,
        comment="Duration of awake time in seconds",
    )
    avg_heart_rate = Column(
        DECIMAL(precision=10, scale=2),
        nullable=True,
        comment="Average heart rate during sleep",
    )
    min_heart_rate = Column(
        Integer,
        nullable=True,
        comment="Minimum heart rate during sleep",
    )
    max_heart_rate = Column(
        Integer,
        nullable=True,
        comment="Maximum heart rate during sleep",
    )
    avg_spo2 = Column(
        DECIMAL(precision=10, scale=2),
        nullable=True,
        comment="Average SpO2 oxygen saturation percentage",
    )
    lowest_spo2 = Column(
        Integer,
        nullable=True,
        comment="Lowest SpO2 reading during sleep",
    )
    highest_spo2 = Column(
        Integer,
        nullable=True,
        comment="Highest SpO2 reading during sleep",
    )
    avg_respiration = Column(
        DECIMAL(precision=10, scale=2),
        nullable=True,
        comment="Average respiration rate",
    )
    lowest_respiration = Column(
        DECIMAL(precision=10, scale=2),
        nullable=True,
        comment="Lowest respiration rate",
    )
    highest_respiration = Column(
        DECIMAL(precision=10, scale=2),
        nullable=True,
        comment="Highest respiration rate",
    )
    avg_stress_level = Column(
        DECIMAL(precision=10, scale=2),
        nullable=True,
        comment="Average stress level during sleep",
    )
    awake_count = Column(
        Integer,
        nullable=True,
        comment="Number of times awakened during sleep",
    )
    restless_moments_count = Column(
        Integer,
        nullable=True,
        comment="Count of restless moments",
    )
    sleep_score_overall = Column(
        Integer,
        nullable=True,
        comment="Overall sleep score (0-100)",
    )
    sleep_score_duration = Column(
        String(50),
        nullable=True,
        comment="Sleep duration score (e.g., GOOD, EXCELLENT, POOR)",
    )
    sleep_score_quality = Column(
        String(50),
        nullable=True,
        comment="Sleep quality score",
    )
    garminconnect_sleep_id = Column(
        String(250),
        nullable=True,
        comment="External Garmin Connect sleep ID",
    )
    sleep_stages = Column(
        JSON,
        nullable=True,
        comment="List of sleep stage intervals as JSON",
    )
    source = Column(
        String(250),
        nullable=True,
        comment="Source of the health sleep data",
    )

    # Define a relationship to the User model
    user = relationship("User", back_populates="health_sleep")
