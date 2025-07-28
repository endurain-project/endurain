from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    String,
    ForeignKey,
    JSON,
    Numeric
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

    gps_point_index_ordered = Column(
        JSON,
        nullable=False,
        comment="Order by which GPS points are passed"
    )

    sub_segment_times = Column(
        JSON,
        nullable=False,
        comment="Sub-segment times tuple (gate, time in seconds)"
    )

    segment_times = Column(
        Numeric,
        nullable=False,
        comment="Time to complete this segment in seconds"
    )
