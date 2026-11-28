"""Activity database models."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    DECIMAL,
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base
from core.sync import TombstoneMixin, UpdatedAtMixin


class Activity(UpdatedAtMixin, Base):
    """Fitness activity record.

    Attributes:
        id: Primary key, a random UUID.
        user_id: Owner user ID.
        parent_activity_id: The multisport parent of a leg; null on every other activity.
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
        gear_id: Associated gear ID, a UUID.
        strava_gear_id: Strava gear ID.
        legacy_strava_activity_id: Legacy Strava activity ID column, written but not read; ``strava_activity_id``
            reads the sources.
        legacy_garminconnect_activity_id: Legacy Garmin Connect activity ID column, likewise.
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
        dedup_key: Legacy idempotency key, neither written nor read: ``activity_sources`` identifies re-imports.
        sources: The activity's sources, the best first.
        location_next_lookup_at: Earliest time the location backfill may look this activity up again.
        thumbnail_next_attempt_at: Earliest time the thumbnail backfill may try this activity again.
        analysis_version: The version of the file analysis that computed the derived values; 0 before versions.
        start_latitude: Latitude of the activity's start point, in degrees; null without a position.
        start_longitude: Longitude of the activity's start point, in degrees; null without a position.
        file_id: Opaque id of the retained source file row, null for a leg, a provider activity and an activity whose
            file was not adopted yet.
        updated_at: When the activity last changed, including a derived change such as its thumbnail or media.
    """

    __tablename__ = "activities"

    __table_args__ = (
        # Legacy: ``activity_sources`` and its unique indexes now make a re-import a no-op. Nothing writes
        # ``dedup_key`` any more, so this index holds only the keys of activities stored before; it goes with the
        # column.
        Index("uq_activities_user_dedup_key", "user_id", "dedup_key", unique=True),
        Index("ix_activities_user_id_updated_at_id", "user_id", "updated_at", "id"),
        # Strava ids are looked up for the owner only; two accounts may link the same Strava athlete.
        Index("ix_activities_user_id_strava_activity_id", "user_id", "strava_activity_id"),
        # The legs of a multisport parent are read through it.
        Index("ix_activities_user_id_parent_activity_id", "user_id", "parent_activity_id"),
        # The reprocess migration walks the activities below the current analysis version in id order.
        Index("ix_activities_analysis_version_id", "analysis_version", "id"),
        CheckConstraint("parent_activity_id <> id", name="ck_activities_parent_not_self"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the activity belongs",
    )
    parent_activity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=True,
        comment="Multisport parent activity ID, set on a leg and null on every other activity",
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
    analysis_version: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default="0",
        default=0,
        comment=(
            "The version of the file analysis that computed the activity's derived values; 0 for one computed "
            "before versions existed"
        ),
    )

    start_latitude: Mapped[float | None] = mapped_column(
        Double,
        nullable=True,
        comment="Latitude of the activity's start point, in degrees; NULL when the activity has no position",
    )
    start_longitude: Mapped[float | None] = mapped_column(
        Double,
        nullable=True,
        comment="Longitude of the activity's start point, in degrees; NULL when the activity has no position",
    )
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("activity_files.id"),
        nullable=True,
        index=True,
        comment="Retained source file the activity was imported from; NULL for a leg or an activity with no file row",
    )

    # SQLAlchemy bumps ``version`` on each ORM flush and adds it to the UPDATE's
    # WHERE clause, raising StaleDataError when the row moved underneath. The
    # If-Match check runs on the row the edit loaded, so this guard covers the
    # rest of the window, between that load and the write.
    #
    # ``version`` changes only for user and provider edits. Derived values written
    # in the background (thumbnail key, resolved location, retry deferrals) use
    # Core UPDATEs that leave it alone, so they never fail a user's If-Match.
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
        comment="Average speed in meters per second (m/s)",
    )
    max_speed: Mapped[Decimal | None] = mapped_column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Max speed in meters per second (m/s)",
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
    gear_id: Mapped[uuid.UUID | None] = mapped_column(
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
    # The two provider id columns are legacy: ``activity_sources`` holds the ids and ``strava_activity_id`` and
    # ``garminconnect_activity_id`` below read them from there. The columns are still written, by ``to_orm`` only,
    # until the release that drops them.
    legacy_strava_activity_id: Mapped[int | None] = mapped_column(
        "strava_activity_id",
        BigInteger,
        nullable=True,
        comment="Strava activity ID",
    )
    legacy_garminconnect_activity_id: Mapped[int | None] = mapped_column(
        "garminconnect_activity_id",
        BigInteger,
        nullable=True,
        comment="Garmin Connect activity ID",
    )
    garminconnect_gear_id: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Garmin Connect gear ID",
    )
    import_info: Mapped[dict[str, Any] | None] = mapped_column(
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
    sources: Mapped[list[ActivitySource]] = relationship(
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: (ActivitySource.precedence.desc(), ActivitySource.received_at, ActivitySource.id),
    )

    def _provider_id(self, kind: str) -> int | None:
        """Return the provider id of the best source of a kind.

        Args:
            kind: The source kind.

        Returns:
            The id, or ``None`` when the activity has no source of that kind.
        """
        return next((source.provider_id for source in self.sources if source.kind == kind), None)

    @property
    def strava_activity_id(self) -> int | None:
        """The Strava activity id of the activity's best Strava source, or ``None``."""
        return self._provider_id("strava")

    @property
    def garminconnect_activity_id(self) -> int | None:
        """The Garmin Connect activity id of the activity's best Garmin source, or ``None``."""
        return self._provider_id("garmin")

    location_next_lookup_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Earliest time the location backfill retries an activity with no resolved location",
    )
    thumbnail_next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Earliest time the thumbnail backfill retries an activity that has no thumbnail",
    )


class ActivityDeletion(TombstoneMixin, Base):
    """A deleted activity, kept so a syncing client learns of the deletion.

    Attributes:
        id: Primary key, a random UUID.
        user_id: Owner of the deleted activity.
        record_id: The id the activity had.
        deleted_at: When the activity was deleted.
    """

    __tablename__ = "activity_deletions"

    __table_args__ = (Index("ix_activity_deletions_user_id_deleted_at_id", "user_id", "deleted_at", "id"),)

    record_id: Mapped[uuid.UUID] = mapped_column(nullable=False, comment="The id the deleted record had")


class ActivitySource(Base):
    """One source an activity was recorded or imported from: a provider activity id or a file's content.

    An activity has one source per identity that reached it. Re-importing a known identity is a no-op.

    Attributes:
        id: Primary key, a random UUID.
        activity_id: The activity the source belongs to; the row goes with it.
        user_id: Owner of the activity, so the unique indexes are per user.
        kind: ``file``, ``garmin`` or ``strava``.
        provider_id: The provider's activity id; set for ``garmin`` and ``strava``.
        file_sha256: Hex SHA-256 of the file; set for ``file``. Copied, not referenced, so the identity outlives the
            retained file.
        session_start: The start of the recording, whole seconds. A multi-activity file shares one hash and one Garmin
            id between its activities, so the start tells them apart. Null for a whole file (a multisport activity)
            and for a Strava activity.
        precedence: How much the source's data is trusted: 2 a device file, 1 a generic file, 0 the Strava API.
        received_at: When the source reached the activity.
    """

    __tablename__ = "activity_sources"

    __table_args__ = (
        # A null ``session_start`` is a value of its own, so a whole file, or a Strava activity, is unique too.
        Index(
            "uq_activity_sources_provider",
            "user_id",
            "kind",
            "provider_id",
            "session_start",
            unique=True,
            postgresql_nulls_not_distinct=True,
            postgresql_where=text("provider_id IS NOT NULL"),
        ),
        Index(
            "uq_activity_sources_file",
            "user_id",
            "file_sha256",
            "session_start",
            unique=True,
            postgresql_nulls_not_distinct=True,
            postgresql_where=text("file_sha256 IS NOT NULL"),
        ),
        Index("ix_activity_sources_activity_id_kind", "activity_id", "kind"),
        CheckConstraint("kind IN ('file', 'garmin', 'strava')", name="ck_activity_sources_kind"),
        CheckConstraint("num_nonnulls(provider_id, file_sha256) = 1", name="ck_activity_sources_one_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    activity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        comment="Activity the source belongs to",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User ID that owns the activity",
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, comment="file, garmin or strava")
    provider_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="Provider activity ID, for a garmin or strava source"
    )
    file_sha256: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="Hex SHA-256 of the file, for a file source"
    )
    session_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Start of the recording in whole seconds; null for a whole file and for a Strava activity",
    )
    precedence: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        comment="2 device file, 1 generic file, 0 Strava API; the higher is the better record",
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When the source reached the activity",
    )
