"""User weekly streak settings database models."""

import uuid

from sqlalchemy import JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class UsersStreakSettings(Base):
    """Per-user configuration for the weekly activity streak.

    Attributes:
        id: Primary key, a random UUID.
        user_id: Foreign key to users table (unique).
        min_activities_per_week: Activities needed in a week
            for it to count toward the streak.
        activity_types: Activity type IDs that count toward
            the streak, or None to count every type.
        show_on_profile: Whether other users can see the
            streak on this user's profile.
    """

    __tablename__ = "users_streak_settings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
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
