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
    """
    SQLAlchemy model representing health sleep data for users.

    This model stores comprehensive sleep tracking information including sleep duration,
    sleep stages, heart rate metrics, SpO2 levels, respiration rates, and sleep quality scores.
    It supports integration with external sources like Garmin Connect.

    Attributes:
        id (int): Primary key for the health sleep record.
        user_id (int): Foreign key referencing the user who owns this sleep data.
        date (Date): Calendar date of the sleep session.
        sleep_start_time_gmt (DateTime): Start time of sleep in GMT timezone.
        sleep_end_time_gmt (DateTime): End time of sleep in GMT timezone.
        sleep_start_time_local (DateTime): Start time of sleep in local timezone.
        sleep_end_time_local (DateTime): End time of sleep in local timezone.
        total_sleep_seconds (int): Total duration of sleep in seconds.
        nap_time_seconds (int): Duration of naps in seconds.
        unmeasurable_sleep_seconds (int): Unmeasurable sleep duration in seconds.
        deep_sleep_seconds (int): Duration of deep sleep in seconds.
        light_sleep_seconds (int): Duration of light sleep in seconds.
        rem_sleep_seconds (int): Duration of REM sleep in seconds.
        awake_sleep_seconds (int): Duration of awake time in seconds.
        avg_heart_rate (int): Average heart rate during sleep.
        min_heart_rate (int): Minimum heart rate during sleep.
        max_heart_rate (int): Maximum heart rate during sleep.
        avg_spo2 (int): Average SpO2 oxygen saturation percentage.
        lowest_spo2 (int): Lowest SpO2 reading during sleep.
        highest_spo2 (int): Highest SpO2 reading during sleep.
        avg_respiration (int): Average respiration rate.
        lowest_respiration (int): Lowest respiration rate.
        highest_respiration (int): Highest respiration rate.
        avg_stress_level (int): Average stress level during sleep.
        awake_count (int): Number of times awakened during sleep.
        restless_moments_count (int): Count of restless moments.
        sleep_score_overall (int): Overall sleep score (0-100).
        sleep_score_duration (str): Sleep duration score (e.g., GOOD, EXCELLENT, POOR).
        sleep_score_quality (str): Sleep quality score.
        garminconnect_sleep_id (str): External Garmin Connect sleep ID.
        sleep_stages (JSON): List of sleep stage intervals as JSON.
        source (str): Source of the health sleep data.
        hrv_status (str): Heart rate variability status.
        resting_heart_rate (int): Resting heart rate during sleep.
        avg_skin_temp_deviation (Decimal): Average skin temperature deviation in Celsius.
        awake_count_score (str): Awake count score.
        rem_percentage_score (str): REM sleep percentage score.
        deep_percentage_score (str): Deep sleep percentage score.
        light_percentage_score (str): Light sleep percentage score.
        avg_sleep_stress (int): Average sleep stress level.
        sleep_stress_score (str): Sleep stress score.
        user (relationship): SQLAlchemy relationship to the User model.
    """

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
        Integer,
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
        Integer,
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
        Integer,
        nullable=True,
        comment="Average respiration rate",
    )
    lowest_respiration = Column(
        Integer,
        nullable=True,
        comment="Lowest respiration rate",
    )
    highest_respiration = Column(
        Integer,
        nullable=True,
        comment="Highest respiration rate",
    )
    avg_stress_level = Column(
        Integer,
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
    hrv_status = Column(
        String(50),
        nullable=True,
        comment="Heart rate variability status",
    )
    resting_heart_rate = Column(
        Integer,
        nullable=True,
        comment="Resting heart rate during sleep",
    )
    avg_skin_temp_deviation = Column(
        DECIMAL(precision=10, scale=2),
        nullable=True,
        comment="Average skin temperature deviation during sleep in Celsius",
    )
    awake_count_score = Column(
        String(50),
        nullable=True,
        comment="Awake count score",
    )
    rem_percentage_score = Column(
        String(50),
        nullable=True,
        comment="REM sleep percentage score",
    )
    deep_percentage_score = Column(
        String(50),
        nullable=True,
        comment="Deep sleep percentage score",
    )
    light_percentage_score = Column(
        String(50),
        nullable=True,
        comment="Light sleep percentage score",
    )
    avg_sleep_stress = Column(
        Integer,
        nullable=True,
        comment="Average sleep stress level",
    )
    sleep_stress_score = Column(
        String(50),
        nullable=True,
        comment="Sleep stress score",
    )

    # Define a relationship to the User model
    user = relationship("User", back_populates="health_sleep")
