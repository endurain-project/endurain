from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    String,
    DECIMAL,
)
from sqlalchemy.orm import relationship
from core.database import Base


class ActivityWorkoutSteps(Base):
    __tablename__ = "activity_workout_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    activity_id = Column(
        Integer,
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Activity ID that the activity workout steps belongs",
    )
    message_index = Column(
        Integer,
        nullable=False,
        comment="Workout step message index",
    )
    duration_type = Column(
        String(length=250), nullable=False, comment="Workout step duration type"
    )
    duration_value = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Workout step duration value",
    )
    target_type = Column(
        String(length=250), nullable=True, comment="Workout step target type"
    )
    target_value = Column(
        Integer,
        nullable=True,
        comment="Workout step target value",
    )
    intensity = Column(
        String(length=250), nullable=True, comment="Workout step intensity type"
    )
    notes = Column(String(length=250), nullable=True, comment="Workout step notes")
    exercise_category = Column(
        Integer,
        nullable=True,
        comment="Workout step exercise category",
    )
    exercise_name = Column(
        Integer,
        nullable=True,
        comment="Exercise name ID",
    )
    exercise_weight = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Workout step exercise weight",
    )
    weight_display_unit = Column(
        String(length=250),
        nullable=True,
        comment="Workout step weight display unit",
    )
    secondary_target_value = Column(
        String(length=250),
        nullable=True,
        comment="Workout step secondary target value",
    )

    # Define a relationship to the Users model
    activity = relationship("Activity", back_populates="activity_workout_steps")
