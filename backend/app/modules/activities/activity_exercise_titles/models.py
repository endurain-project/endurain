"""SQLAlchemy ORM model for activity exercise titles."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class ActivityExerciseTitles(Base):
    """
    Mapping of FIT exercise categories/names to workout step names.

    Attributes:
        id: Primary key.
        exercise_category: FIT exercise category code.
        exercise_name: FIT exercise name identifier.
        wkt_step_name: Workout step name (may include spaces).
    """

    __tablename__ = "activity_exercise_titles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    exercise_category: Mapped[int] = mapped_column(nullable=False, comment="Exercise category")
    exercise_name: Mapped[int] = mapped_column(nullable=False, comment="Exercise name ID")
    wkt_step_name: Mapped[str] = mapped_column(
        String(length=250),
        nullable=False,
        comment="WKT step name (may include spaces)",
    )
