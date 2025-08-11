from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    String,
    ForeignKey,
    JSON,
    Numeric,
    DECIMAL
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.mysql import JSON
from core.database import Base

# Data model for activities table using SQLAlchemy's ORM
class Segments(Base):
    __tablename__ = "segments"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement=True,
        nullable=False,
        comment="ID for the segment"
        )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the Segment belongs to"
        )

    name = Column(
        String(length=250),
        nullable=True,
        comment="Segment name (May include spaces)"
        )

    activity_type = Column(
        Integer,
        nullable=False,
        comment="Activity type")

    gates = Column(
        JSON,
        nullable=False,
        comment="Store gates data"
        )
    
    city = Column(
        String(length=250),
        nullable=True,
        comment="Segment city (May include spaces)"
        )
    
    town = Column(
        String(length=250),
        nullable=True,
        comment="Segment town (May include spaces)"
        )
    
    country = Column(
        String(length=250),
        nullable=True,
        comment="Segment country (May include spaces)"
        )

class ActivitySegment(Base):
    __tablename__ = "activity_segment"

    id = Column(
        Integer,
        primary_key=True,
        autoincrement = True,
        nullable=False,
        comment="ID for the Segment Activity"
    )

    activity_id = Column(
        Integer,
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Activity ID that the ActivitySegment record belongs to"
    )

    segment_id = Column(
        Integer,
        ForeignKey("segments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Segment ID that the ActivitySegment record belongs to"
    )

    lap_number = Column(
        Integer,
        nullable=False,
        comment="Lap number"
    )

    segment_name = Column(
        String(length=250),
        nullable=True,
        comment="Segment name"
    )

    start_time = Column(
        DateTime,
        nullable=False,
        comment="Time when segment was started"
    )

    gate_ordered = Column(
        JSON,
        nullable=False,
        comment="Order by which gates were passed"
    )

    gate_times = Column(
        JSON,
        nullable=True,
        comment="Times when gates were passed"
    )

    gps_point_index_ordered = Column(
        JSON,
        nullable=False,
        comment="Order by which GPS points are passed"
    )

    sub_segment_times = Column(
        JSON,
        nullable=False,
        comment="Sub-segment times in seconds"
    )

    sub_segment_paces = Column(
        JSON,
        nullable=False,
        comment="Sub-segment pace (s/m)"
    )

    segment_time = Column(
        DECIMAL(precision=20, scale=10),
        nullable=False,
        comment="Time to complete this segment in seconds"
    )
    segment_distance = Column(
        Integer,
        nullable=True,
        comment="Segment distance in meters"
    )

    sub_segment_distances = Column(
        JSON,
        nullable=True,
        comment="Sub-segment distances"
    )

    elevation_gain = Column(Integer, nullable=True, comment="Elevation gain in meters")
    elevation_loss = Column(Integer, nullable=True, comment="Elevation loss in meters")
    segment_pace = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Pace seconds per meter (s/m)",
    )
    average_speed = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Average speed seconds per meter (s/m)",
    )
    max_speed = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Max speed seconds per meter (s/m)",
    )
    average_power = Column(Integer, nullable=True, comment="Average power (watts)")
    max_power = Column(Integer, nullable=True, comment="Max power (watts)")
    normalized_power = Column(
        Integer, nullable=True, comment="Normalized power (watts)"
    )
    average_hr = Column(Integer, nullable=True, comment="Average heart rate (bpm)")
    max_hr = Column(Integer, nullable=True, comment="Max heart rate (bpm)")
    average_cad = Column(Integer, nullable=True, comment="Average cadence (rpm)")
    max_cad = Column(Integer, nullable=True, comment="Max cadence (rpm)")
