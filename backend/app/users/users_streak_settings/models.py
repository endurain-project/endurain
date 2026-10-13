"""User weekly streak settings database models."""

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from users.users.models import Users


class UsersStreakSettings(Base):
    """
    Per-user configuration for the weekly activity streak.

    Attributes:
        id: Primary key.
        user_id: Foreign key to users table (unique).
        min_activities_per_week: Activities needed in a week
            for it to count toward the streak.
        activity_types: Activity type IDs that count toward
            the streak, or None to count every type.
        show_on_profile: Whether other users can see the
            streak on this user's profile.
        users: Relationship to Users model.
    """

    __tablename__ = "users_streak_settings"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="User ID that the streak settings belong to",
    )
    min_activities_per_week: Mapped[int] = mapped_column(
        default=1,
        nullable=False,
        comment="Activities needed in a week to keep the streak",
    )
    activity_types: Mapped[list[int] | None] = mapped_column(
        JSON,
        default=None,
        nullable=True,
        comment="Activity type IDs counted for the streak (null = all)",
    )
    show_on_profile: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Show the streak to other users on the profile",
    )

    # Define a relationship to the Users model
    users: Mapped["Users"] = relationship(back_populates="users_streak_settings")
