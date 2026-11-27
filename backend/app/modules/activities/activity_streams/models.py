"""ORM models for activity stream data."""

import uuid
from typing import Any

from sqlalchemy import JSON, REAL, CheckConstraint, Double, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

import modules.activities.activity_streams.constants as activity_streams_constants
from core.database import Base


class ActivityStreams(Base):
    """ORM model for activity stream data.

    Attributes:
        id: Primary key, a random UUID.
        activity_id: FK to the parent activity.
        stream_type: Stream type integer code.
        stream_waypoints: JSON waypoint data.
        strava_activity_stream_id: Strava stream ID.
    """

    __tablename__ = "activities_streams"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    activity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "activities.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
        comment=("Activity ID that the activity stream belongs"),
    )
    stream_type: Mapped[int] = mapped_column(
        nullable=False,
        comment=("Stream type (1-HR, 2-Power, 3-Cadence, 4-Elevation, 5-Velocity, 6-Pace, 7-lat/lon)"),
    )
    stream_waypoints: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        comment="Store waypoints data",
    )
    strava_activity_stream_id: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Strava activity stream ID",
    )


class ActivitySamples(Base):
    """ORM model for the columnar time series of an activity, one row per activity.

    Every channel is an array aligned with ``offsets_ms``: element ``i`` of each channel belongs to the sample at
    ``offsets_ms[i]``. A channel is NULL when the activity has no such channel; an element is NULL where a sample
    has no value. The array columns are stored with PostgreSQL ``lz4`` compression, set by the Alembic revision.

    Attributes:
        activity_id: Primary key and FK to the parent activity.
        offsets_ms: Each sample's time in milliseconds from the activity's start time.
        latitude: Latitude per sample, in degrees.
        longitude: Longitude per sample, in degrees.
        elevation: Elevation per sample, in meters.
        heart_rate: Heart rate per sample, in bpm.
        power: Power per sample, in watts.
        cadence: Cadence per sample, in rpm (spm for running).
        speed: Speed per sample, in m/s.
        temperature: Temperature per sample, in degrees Celsius.
    """

    __tablename__ = "activity_samples"
    __table_args__ = (
        *(
            CheckConstraint(
                f"{name} IS NULL OR cardinality({name}) = cardinality(offsets_ms)",
                name=f"ck_activity_samples_{name}_len",
            )
            for name in activity_streams_constants.SAMPLE_CHANNELS
        ),
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="ck_activity_samples_lat_lon_together"),
    )

    activity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Activity the samples belong to",
    )
    offsets_ms: Mapped[list[int]] = mapped_column(
        ARRAY(Integer),
        nullable=False,
        comment="Each sample's time in milliseconds from the activity start time; may be negative",
    )
    latitude: Mapped[list[float | None] | None] = mapped_column(
        ARRAY(Double), nullable=True, comment="Latitude per sample, in degrees; NULL when the activity has no GPS"
    )
    longitude: Mapped[list[float | None] | None] = mapped_column(
        ARRAY(Double), nullable=True, comment="Longitude per sample, in degrees; NULL when the activity has no GPS"
    )
    elevation: Mapped[list[float | None] | None] = mapped_column(
        ARRAY(REAL), nullable=True, comment="Elevation per sample, in meters; NULL when the activity has none"
    )
    heart_rate: Mapped[list[float | None] | None] = mapped_column(
        ARRAY(REAL), nullable=True, comment="Heart rate per sample, in bpm; NULL when the activity has none"
    )
    power: Mapped[list[float | None] | None] = mapped_column(
        ARRAY(REAL), nullable=True, comment="Power per sample, in watts; NULL when the activity has none"
    )
    cadence: Mapped[list[float | None] | None] = mapped_column(
        ARRAY(REAL),
        nullable=True,
        comment="Cadence per sample, in rpm (spm for running); NULL when the activity has none",
    )
    speed: Mapped[list[float | None] | None] = mapped_column(
        ARRAY(REAL), nullable=True, comment="Speed per sample, in m/s; NULL when the activity has none"
    )
    temperature: Mapped[list[float | None] | None] = mapped_column(
        ARRAY(REAL),
        nullable=True,
        comment="Temperature per sample, in degrees Celsius; NULL when the activity has none",
    )
