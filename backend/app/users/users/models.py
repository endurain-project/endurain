"""User database models."""

from datetime import date as date_type
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from activities.activity.models import Activity
    from followers.models import Follower
    from gears.gear.models import Gear
    from gears.gear_components.models import GearComponents
    from health.health_fasting.models import HealthFasting
    from health.health_poop.models import HealthPoop
    from health.health_sleep.models import HealthSleep
    from health.health_steps.models import HealthSteps
    from health.health_targets.models import HealthTargets
    from health.health_water.models import HealthWater
    from health.health_weight.models import HealthWeight
    from notifications.models import Notification
    from users.users_default_gear.models import UsersDefaultGear
    from users.users_goals.models import UsersGoal
    from users.users_integrations.models import UsersIntegrations
    from users.users_privacy_settings.models import UsersPrivacySettings


class Users(Base):
    """
    User account and profile information.

    Attributes:
        id: Primary key.
        name: User's real name (may include spaces).
        username: Unique username (letters, numbers, dots).
        email: Unique email address (max 250 characters).
        city: User's city.
        birthdate: User's birthdate.
        preferred_language: Preferred language code.
        gender: User's gender (male, female, unspecified).
        units: Measurement units (metric, imperial).
        height: User's height in centimeters.
        max_heart_rate: User maximum heart rate (bpm).
        access_type: User type (regular, admin).
        photo_path: Path to user's photo.
        active: Whether the user is active.
        first_day_of_week: First day of the week
            (sunday, monday, etc.).
        currency: Currency preference (euro, dollar, pound).
        email_verified: Whether the user's email address has
            been verified.
        pending_admin_approval: Whether the user is pending
            admin approval for activation.
        users_integrations: List of integrations.
        users_default_gear: List of default gear.
        users_privacy_settings: List of privacy settings.
        gear: List of gear owned by the user.
        gear_components: List of gear components.
        activities: List of activities performed.
        followers: List of Follower objects representing users
            who follow this user.
        following: List of Follower objects representing users
            this user is following.
        health_sleep: List of health sleep records.
        health_weight: List of health weight records.
        health_steps: List of health steps records.
        health_targets: List of health targets.
        health_fasting: List of health fasting records.
        health_water: List of health water intake records.
        health_poop: List of health poop records.
        notifications: List of notifications.
        goals: List of user goals.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        comment="User real name (May include spaces)",
    )
    username: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        unique=True,
        index=True,
        comment="User username (letters, numbers, and dots allowed)",
    )
    email: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        unique=True,
        index=True,
        comment="User email (max 250 characters)",
    )
    city: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="User city",
    )
    birthdate: Mapped[date_type | None] = mapped_column(
        nullable=True,
        comment="User birthdate (date)",
    )
    preferred_language: Mapped[str] = mapped_column(
        String(35),
        nullable=False,
        comment="User preferred BCP 47 language tag (en, pt-PT, zh-Hans, others)",
    )
    gender: Mapped[str] = mapped_column(
        String(20),
        default="male",
        nullable=False,
        comment="User gender (male, female, unspecified)",
    )
    units: Mapped[str] = mapped_column(
        String(20),
        default="metric",
        nullable=False,
        comment="User units (metric, imperial)",
    )
    height: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="User height in centimeters",
    )
    max_heart_rate: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="User maximum heart rate (bpm)",
    )
    access_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="User type (regular, admin)",
    )
    photo_path: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="User photo path",
    )
    active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        comment="Whether the user is active (true - yes, false - no)",
    )
    first_day_of_week: Mapped[str] = mapped_column(
        String(20),
        default="monday",
        nullable=False,
        comment="User first day of week (sunday, monday, etc.)",
    )
    currency: Mapped[str] = mapped_column(
        String(20),
        default="euro",
        nullable=False,
        comment="User currency (euro, dollar, pound)",
    )
    email_verified: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment=("Whether the user's email address has been verified (true - yes, false - no)"),
    )
    pending_admin_approval: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment=("Whether the user is pending admin approval for activation (true - yes, false - no)"),
    )

    # Relationships
    users_integrations: Mapped[list["UsersIntegrations"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
    )
    users_default_gear: Mapped[list["UsersDefaultGear"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
    )
    users_privacy_settings: Mapped[list["UsersPrivacySettings"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
    )
    gear: Mapped[list["Gear"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
    )
    gear_components: Mapped[list["GearComponents"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
    )
    activities: Mapped[list["Activity"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
    )
    followers: Mapped[list["Follower"]] = relationship(
        back_populates="following",
        cascade="all, delete-orphan",
        foreign_keys="Follower.following_id",
    )
    following: Mapped[list["Follower"]] = relationship(
        back_populates="follower",
        cascade="all, delete-orphan",
        foreign_keys="Follower.follower_id",
    )
    health_sleep: Mapped[list["HealthSleep"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
    )
    health_weight: Mapped[list["HealthWeight"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
    )
    health_steps: Mapped[list["HealthSteps"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
    )
    health_targets: Mapped[list["HealthTargets"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
    )
    health_fasting: Mapped[list["HealthFasting"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
    )
    health_water: Mapped[list["HealthWater"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
    )
    health_poop: Mapped[list["HealthPoop"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
    )
    goals: Mapped[list["UsersGoal"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
    )
