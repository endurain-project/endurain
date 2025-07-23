from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    String,
    DECIMAL,
    DateTime,
)
from sqlalchemy.orm import relationship
from core.database import Base


class ActivitySets(Base):
    __tablename__ = "activity_sets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    activity_id = Column(
        Integer,
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Activity ID that the activity lap belongs",
    )
    duration = Column(
        DECIMAL(precision=20, scale=10),
        nullable=False,
        comment="Workout set duration",
    )
    repetitions = Column(
        Integer,
        nullable=True,
        comment="Repetitions number",
    )
    weight = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Workout set exercise weight",
    )
    set_type = Column(String(length=250), nullable=False, comment="Workout set type")
    start_time = Column(
        DateTime, nullable=False, comment="Workout set start date (DATETIME)"
    )
    category = Column(
        Integer,
        nullable=True,
        comment="Category name",
    )
    category_subtype = Column(
        Integer,
        nullable=True,
        comment="Category sub type number",
    )

    # Define a relationship to the Activity model
    activity = relationship("Activity", back_populates="activity_sets")
