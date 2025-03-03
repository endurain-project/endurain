from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    BigInteger,
    DECIMAL,
    DateTime,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.mysql import JSON
from core.database import Base


class ActivitySplits(Base):
    __tablename__ = "activities_splits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    activity_id = Column(
        Integer,
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Activity ID that the activity split belongs",
    )
    split_type = Column(Integer, nullable=False, comment="Split type")
    total_elapsed_time = Column(
        DECIMAL(precision=20, scale=10),
        nullable=False,
        comment="Split total elapsed time (s)",
    )
    total_timer_time = Column(
        DECIMAL(precision=20, scale=10),
        nullable=False,
        comment="Split total timer time (s)",
    )
    total_distance = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Split total distance (m)",
    )
    average_speed = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Average speed seconds per meter (s/m)",
    )
    start_time = Column(DateTime, nullable=False, comment="Split start date (DATETIME)")
    total_ascent = Column(
        Integer,
        nullable=True,
        comment="Split total ascent (m)",
    )
    total_descent = Column(
        Integer,
        nullable=True,
        comment="Split total descent (m)",
    )
    start_position_lat = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Split start position latitude",
    )
    start_position_long = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Split start position longitude",
    )
    end_position_lat = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Split end position latitude",
    )
    end_position_long = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Split end position longitude",
    )
    max_speed = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Max speed seconds per meter (s/m)",
    )
    end_time = Column(DateTime, nullable=False, comment="Split end date (DATETIME)")
    total_calories = Column(
        Integer,
        nullable=True,
        comment="Split total calories",
    )
    start_elevation = Column(
        Integer,
        nullable=True,
        comment="Split start elevation (m)",
    )

    # Define a relationship to the User model
    activity = relationship("Activity", back_populates="activities_splits")
