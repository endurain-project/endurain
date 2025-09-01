from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from core.database import Base


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
    interval = Column(
        String(length=250),
        nullable=False,
        comment="Goal interval (e.g., 'daily', 'weekly', 'monthly', 'yearly')",
    )
    activity_type = Column(
        Integer,
        nullable=False,
        comment="Activity type",
    )
    goal_type = Column(
        Integer,
        nullable=False,
        comment="Goal type",
    )
    goal_calories = Column(
        Integer,
        nullable=True,
        comment="Goal calories in kcal (e.g., 5000 for 5000 kcal)",
    )
    goal_activities_number = Column(
        Integer,
        nullable=True,
        comment="Goal activities number (e.g., 5 for 5 activities)",
    )
    goal_distance = Column(
        Integer,
        nullable=True,
        comment="Goal distance in meters (e.g., 10000 for 10 km)",
    )
    goal_elevation = Column(
        Integer,
        nullable=True,
        comment="Goal elevation in meters (e.g., 1000 for 1000 m)",
    )
    goal_duration = Column(
        Integer,
        nullable=True,
        comment="Goal duration in seconds (e.g., 3600 for 1 hours)",
    )

    # Relationship to User
    user = relationship("User", back_populates="goals")
