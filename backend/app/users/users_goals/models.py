"""User fitness goals database models."""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base


class UsersGoal(Base):
    """
    User fitness goal tracking model.

    Attributes:
        id: Primary key.
        user_id: Foreign key to users table.
        interval: Goal time interval (daily, weekly, monthly,
            yearly).
        activity_type: Type of activity for the goal.
        goal_type: Type of goal metric.
        goal_calories: Target calories in kcal.
        goal_activities_number: Target number of activities.
        goal_distance: Target distance in meters.
        goal_elevation: Target elevation gain in meters.
        goal_duration: Target duration in seconds.
        user: Relationship to Users model.
    """

    __tablename__ = "users_goals"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the goals belongs",
    )
    interval: Mapped[str] = mapped_column(
        String(length=250),
        nullable=False,
        comment=("Goal interval (e.g., 'daily', 'weekly', 'monthly', 'yearly')"),
    )
    activity_type: Mapped[str] = mapped_column(
        String(length=50),
        nullable=False,
        comment="Activity type (e.g., 'run', 'bike', 'swim')",
    )
    goal_type: Mapped[str] = mapped_column(
        String(length=50),
        nullable=False,
        comment="Goal type (e.g., 'calories', 'distance', 'duration')",
    )
    goal_calories: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Goal calories in kcal (e.g., 5000 for 5000 kcal)",
    )
    goal_activities_number: Mapped[int | None] = mapped_column(
        nullable=True,
        comment=("Goal activities number (e.g., 5 for 5 activities)"),
    )
    goal_distance: Mapped[int | None] = mapped_column(
        nullable=True,
        comment=("Goal distance in meters (e.g., 10000 for 10 km)"),
    )
    goal_elevation: Mapped[int | None] = mapped_column(
        nullable=True,
        comment=("Goal elevation in meters (e.g., 1000 for 1000 m)"),
    )
    goal_duration: Mapped[int | None] = mapped_column(
        nullable=True,
        comment=("Goal duration in seconds (e.g., 3600 for 1 hours)"),
    )

    # Relationship to User
    # TODO: Change to Mapped["User"] when all modules use mapped
    users = relationship("Users", back_populates="goals")
