from datetime import date as date_type, datetime
from decimal import Decimal
from sqlalchemy import ForeignKey, JSON, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base


class HealthSleep(Base):
    """
    User sleep tracking data with metrics and quality scores.

    Attributes:
        id: Primary key.
        user_id: Foreign key to users table.
        date: Calendar date of sleep session.
        sleep_start_time_gmt: Sleep start in GMT.
        sleep_end_time_gmt: Sleep end in GMT.
        sleep_start_time_local: Sleep start in local time.
        sleep_end_time_local: Sleep end in local time.
        total_sleep_seconds: Total sleep duration.
        nap_time_seconds: Nap duration.
        unmeasurable_sleep_seconds: Unmeasurable sleep.
        deep_sleep_seconds: Deep sleep duration.
        light_sleep_seconds: Light sleep duration.
        rem_sleep_seconds: REM sleep duration.
        awake_sleep_seconds: Awake time during sleep.
        avg_heart_rate: Average heart rate.
        min_heart_rate: Minimum heart rate.
        max_heart_rate: Maximum heart rate.
        avg_spo2: Average SpO2 percentage.
        lowest_spo2: Lowest SpO2 reading.
        highest_spo2: Highest SpO2 reading.
        avg_respiration: Average respiration rate.
        lowest_respiration: Lowest respiration.
        highest_respiration: Highest respiration.
        avg_stress_level: Average stress level.
        awake_count: Times awakened.
        restless_moments_count: Restless moments.
        sleep_score_overall: Overall score (0-100).
        sleep_score_duration: Duration score label.
        sleep_score_quality: Quality score label.
        garminconnect_sleep_id: Garmin Connect ID.
        sleep_stages: Sleep stage intervals (JSON).
        source: Data source.
        hrv_status: HRV status.
        resting_heart_rate: Resting heart rate.
        avg_skin_temp_deviation: Skin temp deviation.
        awake_count_score: Awake count score.
        rem_percentage_score: REM percentage score.
        deep_percentage_score: Deep percentage score.
        light_percentage_score: Light percentage score.
        avg_sleep_stress: Average sleep stress.
        sleep_stress_score: Sleep stress score.
        user: Relationship to Users model.
    """

    __tablename__ = "health_sleep"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the health_sleep belongs",
    )
    date: Mapped[date_type] = mapped_column(
        nullable=False,
        index=True,
        comment="Calendar date of the sleep session",
    )
    sleep_start_time_gmt: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Start time of sleep in GMT",
    )
    sleep_end_time_gmt: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="End time of sleep in GMT",
    )
    sleep_start_time_local: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="Start time of sleep in local time",
    )
    sleep_end_time_local: Mapped[datetime | None] = mapped_column(
        nullable=True,
        comment="End time of sleep in local time",
    )
    total_sleep_seconds: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Total duration of sleep in seconds",
    )
    nap_time_seconds: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Duration of naps in seconds",
    )
    unmeasurable_sleep_seconds: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Unmeasurable sleep duration in seconds",
    )
    deep_sleep_seconds: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Duration of deep sleep in seconds",
    )
    light_sleep_seconds: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Duration of light sleep in seconds",
    )
    rem_sleep_seconds: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Duration of REM sleep in seconds",
    )
    awake_sleep_seconds: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Duration of awake time in seconds",
    )
    avg_heart_rate: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Average heart rate during sleep",
    )
    min_heart_rate: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Minimum heart rate during sleep",
    )
    max_heart_rate: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Maximum heart rate during sleep",
    )
    avg_spo2: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Average SpO2 oxygen saturation percentage",
    )
    lowest_spo2: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Lowest SpO2 reading during sleep",
    )
    highest_spo2: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Highest SpO2 reading during sleep",
    )
    avg_respiration: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Average respiration rate",
    )
    lowest_respiration: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Lowest respiration rate",
    )
    highest_respiration: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Highest respiration rate",
    )
    avg_stress_level: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Average stress level during sleep",
    )
    awake_count: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Number of times awakened during sleep",
    )
    restless_moments_count: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Count of restless moments",
    )
    sleep_score_overall: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Overall sleep score (0-100)",
    )
    sleep_score_duration: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Sleep duration score (e.g., GOOD, EXCELLENT, POOR)",
    )
    sleep_score_quality: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Sleep quality score",
    )
    garminconnect_sleep_id: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="External Garmin Connect sleep ID",
    )
    sleep_stages: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="List of sleep stage intervals as JSON",
    )
    source: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Source of the health sleep data",
    )
    hrv_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Heart rate variability status",
    )
    resting_heart_rate: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Resting heart rate during sleep",
    )
    avg_skin_temp_deviation: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=True,
        comment="Average skin temperature deviation during sleep in Celsius",
    )
    awake_count_score: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Awake count score",
    )
    rem_percentage_score: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="REM sleep percentage score",
    )
    deep_percentage_score: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Deep sleep percentage score",
    )
    light_percentage_score: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Light sleep percentage score",
    )
    avg_sleep_stress: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Average sleep stress level",
    )
    sleep_stress_score: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Sleep stress score",
    )

    # Define a relationship to the Users model
    # TODO: Change to Mapped["User"] when all modules use mapped
    users = relationship("Users", back_populates="health_sleep")
