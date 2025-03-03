from sqlalchemy import (
    Column,
    Integer,
    String,
)
from core.database import Base


class ActivityExerciseTitles(Base):
    __tablename__ = "activity_exercise_titles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exercise_category = Column(
        String(length=250),
        nullable=False,
        comment="Exercise category (May include spaces and may be a number)",
    )
    exercise_name = Column(
        Integer,
        unique=True,
        nullable=False,
        comment="Exercise name ID",
    )
    wkt_step_name = Column(
        String(length=250), nullable=False, comment="WKT step name (May include spaces)"
    )
