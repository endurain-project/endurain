from sqlalchemy import (
    Column,
    Integer,
    String,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from core.database import Base


class UserGoal(Base):
    """
    Represents a user's activity goal within the application.

    Attributes:
        id (int): Primary key for the user goal.
        user_id (int): Foreign key referencing the user to whom the goal belongs.
        activity_type (int): Type of activity for which the goal is set.
        interval (str): Interval for the goal (e.g., 'daily', 'weekly', 'monthly').
        goal_duration (int): Target duration for the goal in hours.
        goal_distance (int): Target distance for the goal in meters.
        goal_elevation (int): Target elevation gain for the goal in meters.
        goal_calories (int): Target calories to burn for the goal in kcal.
        goal_steps (int): Target number of steps for the goal.
        goal_count (int): Target count of activities for the goal.
        user (User): Relationship to the User model, representing the goal's owner.
    """
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
