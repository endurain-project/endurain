"""Activity database models."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DECIMAL,
    JSON,
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Activity(Base):
    """
    Fitness activity record.

    Attributes:
        id: Primary key.
        user_id: Owner user ID.
        name: Activity name.
        description: Public description.
        private_notes: Private notes (owner only).
        distance: Distance in meters.
        activity_type: Numeric sport type code.
        start_time: Activity start (timezone-aware).
        end_time: Activity end (timezone-aware).
        timezone: IANA timezone string.
        total_elapsed_time: Total elapsed time (s).
        total_timer_time: Active timer time (s).
        city: City of the activity.
        town: Town of the activity.
        country: Country of the activity.
        created_at: Creation timestamp.
        elevation_gain: Elevation gain (m).
        elevation_loss: Elevation loss (m).
        pace: Pace in s/m.
        average_speed: Average speed (m/s).
        max_speed: Maximum speed (m/s).
        average_power: Average power (W).
        max_power: Maximum power (W).
        normalized_power: Normalized power (W).
        average_hr: Average heart rate (bpm).
        max_hr: Maximum heart rate (bpm).
        average_cad: Average cadence (rpm).
        max_cad: Maximum cadence (rpm).
        workout_feeling: Workout feeling (0-100).
        workout_rpe: Workout RPE (10-100).
        calories: Calories consumed (kcal).
        visibility: 0 - public, 1 - followers, 2 - private.
        gear_id: Associated gear ID.
        strava_gear_id: Strava gear ID.
        strava_activity_id: Strava activity ID.
        garminconnect_activity_id: Garmin Connect activity ID.
        garminconnect_gear_id: Garmin Connect gear ID.
        import_info: Additional import metadata.
        is_hidden: Whether the activity is hidden.
        hide_start_time: Hide start time from others.
        hide_location: Hide location from others.
        hide_map: Hide map from others.
        hide_hr: Hide heart rate from others.
        hide_power: Hide power from others.
        hide_cadence: Hide cadence from others.
        hide_elevation: Hide elevation from others.
        hide_speed: Hide speed from others.
        hide_pace: Hide pace from others.
        hide_laps: Hide laps from others.
        hide_workout_sets_steps: Hide workout sets and steps.
        hide_gear: Hide gear from others.
        tracker_manufacturer: Device manufacturer.
        tracker_model: Device model.
        map_thumbnail_path: Path to the static map thumbnail.
        dedup_key: Stable idempotency key (provider id now, content hash later) used to no-op re-imports.
    """

    __tablename__ = "activities"

    __table_args__ = (
        # Idempotency is enforced by the database, not just checked in the
        # ingestion service. That check is read-then-write, so two concurrent
        # imports of the same file or provider activity could both see "not
        # found" and both insert — which the bulk-import ThreadPoolExecutor and
        # durable-job retries make a realistic race rather than a theoretical
        # one. The service now catches the resulting IntegrityError and returns
        # the winning row, so the constraint is what makes re-import a true
        # no-op. NULL dedup_keys stay unconstrained (Postgres treats NULLs as
        # distinct), so activities with no stable identity are unaffected.
        Index("uq_activities_user_dedup_key", "user_id", "dedup_key", unique=True),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the activity belongs",
    )
    name: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Activity name (May include spaces)",
    )
    description: Mapped[str | None] = mapped_column(
        String(2500),
        nullable=True,
        comment="Activity description (May include spaces)",
    )
    private_notes: Mapped[str | None] = mapped_column(
        String(2500),
        nullable=True,
        comment="Activity private notes (May include spaces)",
    )
    distance: Mapped[int] = mapped_column(
        nullable=False,
        comment="Distance in meters",
    )
    activity_type: Mapped[int] = mapped_column(
        nullable=False,
        comment=("Gear type (1 - mountain bike, 2 - gravel bike, ...)"),
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Activity start date (DATETIME)",
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Activity end date (DATETIME)",
    )
    timezone: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Activity timezone (May include spaces)",
    )
    total_elapsed_time: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=False,
        comment="Activity total elapsed time (s)",
    )
    total_timer_time: Mapped[Decimal] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=False,
        comment="Activity total timer time (s)",
    )
    city: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Activity city (May include spaces)",
    )
    town: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Activity town (May include spaces)",
    )
    country: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Activity country (May include spaces)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Activity creation date (DATETIME)",
    )
    version: Mapped[int] = mapped_column(
        nullable=False,
        server_default="1",
        default=1,
        comment="Optimistic-concurrency counter, surfaced to clients as the ETag",
    )

    # SQLAlchemy bumps ``version`` on each ORM flush and adds it to the UPDATE's
    # WHERE clause, raising StaleDataError when the row moved underneath. That
    # closes the window an If-Match check alone leaves open, between reading the
    # version and writing the row.
    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012
    elevation_gain: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Elevation gain in meters",
    )
    elevation_loss: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Elevation loss in meters",
    )
    pace: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Pace seconds per meter (s/m)",
    )
    average_speed: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Average speed seconds per meter (s/m)",
    )
    max_speed: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Max speed seconds per meter (s/m)",
    )
    average_power: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Average power (watts)",
    )
    max_power: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Max power (watts)",
    )
    normalized_power: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Normalized power (watts)",
    )
    average_hr: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Average heart rate (bpm)",
    )
    max_hr: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Max heart rate (bpm)",
    )
    average_cad: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Average cadence (rpm)",
    )
    max_cad: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Max cadence (rpm)",
    )
    workout_feeling: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Workout feeling (0 to 100)",
    )
    workout_rpe: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Workout RPE (10 to 100)",
    )
    calories: Mapped[int | None] = mapped_column(
        nullable=True,
        comment=("The number of kilocalories consumed during this activity"),
    )
    visibility: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
        comment="0 - public, 1 - followers, 2 - private",
    )
    gear_id: Mapped[int | None] = mapped_column(
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID associated with this activity",
    )
    strava_gear_id: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Strava gear ID",
    )
    strava_activity_id: Mapped[int | None] = mapped_column(
        BigInteger,
        unique=True,
        nullable=True,
        comment="Strava activity ID",
    )
    garminconnect_activity_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="Garmin Connect activity ID",
    )
    garminconnect_gear_id: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Garmin Connect gear ID",
    )
    import_info: Mapped[dict | None] = mapped_column(
        JSON,
        default=None,
        nullable=True,
        doc="Additional import information",
    )
    is_hidden: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment=("Indicates if the activity is hidden (e.g., duplicate activity waiting to be reviewed by the user)"),
    )
    hide_start_time: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Hide activity start time",
    )
    hide_location: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Hide activity location",
    )
    hide_map: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Hide activity map",
    )
    hide_hr: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Hide activity heart rate",
    )
    hide_power: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Hide activity power",
    )
    hide_cadence: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Hide activity cadence",
    )
    hide_elevation: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Hide activity elevation",
    )
    hide_speed: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Hide activity speed",
    )
    hide_pace: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Hide activity pace",
    )
    hide_laps: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Hide activity laps",
    )
    hide_workout_sets_steps: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Hide activity workout sets and steps",
    )
    hide_gear: Mapped[bool] = mapped_column(
        nullable=False,
        comment="Hide activity gear",
    )
    tracker_manufacturer: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment=("Tracker manufacturer (e.g., Garmin, Suunto, Polar)"),
    )
    tracker_model: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment=("Tracker model (e.g., Forerunner 245, Ambit3 Peak, Vantage V2)"),
    )
    map_thumbnail_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment=("Relative path to the pre-generated static map thumbnail image"),
    )
    total_cycles: Mapped[int | None] = mapped_column(
        nullable=True,
        comment=("Total number of cycles (e.g., pedal strokes) recorded"),
    )
    dedup_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment=("Stable idempotency key (provider id or content hash) to no-op re-imports"),
    )
