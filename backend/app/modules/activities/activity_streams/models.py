"""ORM models for activity stream data."""

import uuid
from typing import Any

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

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
