"""Activity sets models."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class ActivitySets(Base):
    """
    Represents a workout set within an activity.

    Attributes:
        id: Primary key.
        activity_id: FK to activities table.
        duration: Workout set duration.
        repetitions: Repetitions count.
        weight: Exercise weight.
        set_type: Workout set type.
        start_time: Workout set start datetime.
        category: Category identifier.
        category_subtype: Category sub type.
    """

    __tablename__ = "activity_sets"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    activity_id: Mapped[int] = mapped_column(
        ForeignKey(
            "activities.id",
            ondelete="CASCADE",
        ),
        index=True,
        comment=("Activity ID that the activity lap belongs"),
    )
    duration: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=10),
        comment="Workout set duration",
    )
    repetitions: Mapped[int | None] = mapped_column(
        comment="Repetitions number",
    )
    weight: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=20, scale=10),
        comment="Workout set exercise weight",
    )
    set_type: Mapped[str] = mapped_column(
        String(length=250),
        comment="Workout set type",
    )
    start_time: Mapped[datetime] = mapped_column(
        # The column is TIMESTAMP WITH TIME ZONE in the database (see the
        # v0_18_0 migration); without an explicit type SQLAlchemy infers a naive
        # DateTime, which both loses the offset on load and makes Alembic
        # autogenerate keep proposing a downgrade back to naive.
        DateTime(timezone=True),
        comment="Workout set start date",
    )
    category: Mapped[int | None] = mapped_column(
        comment="Category name",
    )
    category_subtype: Mapped[int | None] = mapped_column(
        comment="Category sub type number",
    )
