"""Activity workout steps models."""

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.activities.activity.models import Activity


class ActivityWorkoutSteps(Base):
    """
    Activity workout step records.

    Attributes:
        id: Primary key.
        activity_id: FK to activities table.
        message_index: Workout step message index.
        duration_type: Workout step duration type.
        duration_value: Workout step duration value.
        target_type: Workout step target type.
        target_value: Workout step target value.
        intensity: Workout step intensity type.
        notes: Workout step notes.
        exercise_category: Workout step exercise
            category.
        exercise_name: Exercise name ID.
        exercise_weight: Workout step exercise weight.
        weight_display_unit: Workout step weight display
            unit.
        secondary_target_value: Workout step secondary
            target value.
        activity: Relationship to Activity model.
    """

    __tablename__ = "activity_workout_steps"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    activity_id: Mapped[int] = mapped_column(
        ForeignKey(
            "activities.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
        comment=("Activity ID that the activity workout steps belongs"),
    )
    message_index: Mapped[int] = mapped_column(
        nullable=False,
        comment="Workout step message index",
    )
    duration_type: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        comment="Workout step duration type",
    )
    duration_value: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=20, scale=10),
        nullable=True,
        comment="Workout step duration value",
    )
    target_type: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Workout step target type",
    )
    target_value: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Workout step target value",
    )
    intensity: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Workout step intensity type",
    )
    notes: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Workout step notes",
    )
    exercise_category: Mapped[int | None] = mapped_column(
        nullable=True,
        comment=("Workout step exercise category"),
    )
    exercise_name: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Exercise name ID",
    )
    exercise_weight: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=20, scale=10),
        nullable=True,
        comment=("Workout step exercise weight"),
    )
    weight_display_unit: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment=("Workout step weight display unit"),
    )
    secondary_target_value: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment=("Workout step secondary target value"),
    )

    # Define a relationship to the Activity model
    activity: Mapped["Activity"] = relationship(
        back_populates="activity_workout_steps",
    )
