"""User privacy settings database models."""

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base


class UsersPrivacySettings(Base):
    """
    User privacy settings for activity visibility control.

    Attributes:
        id: Primary key.
        user_id: Foreign key to users table (unique).
        default_activity_visibility: Default visibility level
            (public, followers, private).
        hide_activity_start_time: Hide activity start time.
        hide_activity_location: Hide activity location.
        hide_activity_map: Hide activity map.
        hide_activity_hr: Hide activity heart rate.
        hide_activity_power: Hide activity power.
        hide_activity_cadence: Hide activity cadence.
        hide_activity_elevation: Hide activity elevation.
        hide_activity_speed: Hide activity speed.
        hide_activity_pace: Hide activity pace.
        hide_activity_laps: Hide activity laps.
        hide_activity_workout_sets_steps: Hide activity workout
            sets and steps.
        hide_activity_gear: Hide activity gear.
        user: Relationship to Users model.
    """

    __tablename__ = "users_privacy_settings"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="User ID that the privacy settings belongs",
    )
    default_activity_visibility: Mapped[str] = mapped_column(
        String(20),
        default="public",
        nullable=False,
        comment="public, followers, private",
    )
    hide_activity_start_time: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Hide activity start time",
    )
    hide_activity_location: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Hide activity location",
    )
    hide_activity_map: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Hide activity map",
    )
    hide_activity_hr: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Hide activity heart rate",
    )
    hide_activity_power: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Hide activity power",
    )
    hide_activity_cadence: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Hide activity cadence",
    )
    hide_activity_elevation: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Hide activity elevation",
    )
    hide_activity_speed: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Hide activity speed",
    )
    hide_activity_pace: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Hide activity pace",
    )
    hide_activity_laps: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Hide activity laps",
    )
    hide_activity_workout_sets_steps: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Hide activity workout sets and steps",
    )
    hide_activity_gear: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Hide activity gear",
    )

    # Define a relationship to the Users model
    # TODO: Change to Mapped["User"] when all modules use mapped
    users = relationship("Users", back_populates="users_privacy_settings")
