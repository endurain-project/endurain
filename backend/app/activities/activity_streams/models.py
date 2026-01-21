from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    BigInteger,
    JSON,
)
from sqlalchemy.orm import relationship
from core.database import Base


class ActivityStreams(Base):
    __tablename__ = "activities_streams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    activity_id = Column(
        Integer,
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Activity ID that the activity stream belongs",
    )
    stream_type = Column(
        Integer,
        nullable=False,
        comment="Stream type (1 - HR, 2 - Power, 3 - Cadence, 4 - Elevation, 5 - Velocity, 6 - Pace, 7 - lat/lon)",
    )
    stream_waypoints = Column(JSON, nullable=False, comment="Store waypoints data")
    strava_activity_stream_id = Column(
        BigInteger, nullable=True, comment="Strava activity stream ID"
    )

    # Define a relationship to the Users model
    activity = relationship("Activity", back_populates="activities_streams")
