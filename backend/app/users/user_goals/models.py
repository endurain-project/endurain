from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from core.database import Base


# Data model for users_goals table using SQLAlchemy's ORM
class UserGoal(Base):
    __tablename__ = "users_goals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the goals belongs",
    )
    activity_type = Column(
        Integer,
        nullable=False,
        comment="Activity type",
    )
    interval = Column(
        String(length=250),
        nullable=False,
        comment="Goal interval (e.g., 'daily', 'weekly', 'monthly')",
    )
    goal_duration = Column(
        Integer,
        nullable=False,
        comment="Goal duration in hours (e.g., 10 for 10 hours)",
    )
    goal_distance = Column(
        Integer,
        nullable=False,
        comment="Goal distance in meters (e.g., 10000 for 10 km)",
    )
    goal_elevation = Column(
        Integer,
        nullable=False,
        comment="Goal elevation in meters (e.g., 1000 for 1000 m)",
    )
    goal_calories = Column(
        Integer,
        nullable=False,
        comment="Goal calories in kcal (e.g., 5000 for 5000 kcal)",
    )
    goal_steps = Column(
        Integer,
        nullable=False,
        comment="Goal steps (e.g., 10000 for 10,000 steps)",
    )
    goal_count = Column(
        Integer,
        nullable=False,
        comment="Goal count (e.g., 5 for 5 activities)",
    )

    # Relationship to User
    user = relationship("User", back_populates="goals")
