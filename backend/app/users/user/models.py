"""User database models."""

from datetime import date as date_type
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base

import followers.models as followers_models


class User(Base):
    """
    User account and profile information.

    Attributes:
        id: Primary key.
        name: User's real name (may include spaces).
        username: Unique username (letters, numbers, dots).
        email: Unique email address (max 250 characters).
        password: User's password hash.
        city: User's city.
        birthdate: User's birthdate.
        preferred_language: Preferred language code.
        gender: User's gender (male, female, unspecified).
        units: Measurement units (1=metric, 2=imperial).
        height: User's height in centimeters.
        max_heart_rate: User maximum heart rate (bpm).
        access_type: User type (regular, admin).
        photo_path: Path to user's photo.
        active: Whether the user is active.
        first_day_of_week: First day of the week
            (sunday, monday, etc.).
        currency: Currency preference (1=euro, 2=dollar, 3=pound).
        mfa_enabled: Whether multi-factor authentication is
            enabled.
        mfa_secret: MFA secret for TOTP generation
            (encrypted at rest).
        email_verified: Whether the user's email address has
            been verified.
        pending_admin_approval: Whether the user is pending
            admin approval for activation.
        users_sessions: List of session objects.
        password_reset_tokens: List of password reset tokens.
        sign_up_tokens: List of sign-up tokens.
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
        notifications: List of notifications.
        goals: List of user goals.
        user_identity_providers: List of identity providers
            linked to the user.
        oauth_states: List of OAuth states for the user.
        mfa_backup_codes: List of MFA backup codes.
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
    password: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        comment="User password (hash)",
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
        String(5),
        nullable=False,
        comment="User preferred language (en, pt, others)",
    )
    gender: Mapped[str] = mapped_column(
        String(20),
        default="male",
        nullable=False,
        comment="User gender (male, female, unspecified)",
    )
    units: Mapped[int] = mapped_column(
        default=1,
        nullable=False,
        comment="User units (one digit)(1 - metric, 2 - imperial)",
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
    currency: Mapped[int] = mapped_column(
        default=1,
        nullable=False,
        comment=("User currency (one digit)" "(1 - euro, 2 - dollar, 3 - pound)"),
    )
    mfa_enabled: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Whether MFA is enabled for this user",
    )
    mfa_secret: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment=("User MFA secret for TOTP generation " "(encrypted at rest)"),
    )
    email_verified: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment=(
            "Whether the user's email address has been verified "
            "(true - yes, false - no)"
        ),
    )
    pending_admin_approval: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment=(
            "Whether the user is pending admin approval for "
            "activation (true - yes, false - no)"
        ),
    )

    # Relationships
    # TODO: Change to Mapped["ModelName"] when all modules use mapped
    users_sessions = relationship(
        "UsersSessions",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    password_reset_tokens = relationship(
        "PasswordResetToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    sign_up_tokens = relationship(
        "SignUpToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    users_integrations = relationship(
        "UsersIntegrations",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    users_default_gear = relationship(
        "UsersDefaultGear",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    users_privacy_settings = relationship(
        "UsersPrivacySettings",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    gear = relationship(
        "Gear",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    gear_components = relationship(
        "GearComponents",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    activities = relationship(
        "Activity",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    followers = relationship(
        "Follower",
        back_populates="following",
        cascade="all, delete-orphan",
        foreign_keys=[followers_models.Follower.following_id],
    )
    following = relationship(
        "Follower",
        back_populates="follower",
        cascade="all, delete-orphan",
        foreign_keys=[followers_models.Follower.follower_id],
    )
    health_sleep = relationship(
        "HealthSleep",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    health_weight = relationship(
        "HealthWeight",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    health_steps = relationship(
        "HealthSteps",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    health_targets = relationship(
        "HealthTargets",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    notifications = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    goals = relationship(
        "UserGoal",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    user_identity_providers = relationship(
        "UserIdentityProvider",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    oauth_states = relationship(
        "OAuthState",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    mfa_backup_codes = relationship(
        "MFABackupCode",
        back_populates="user",
        cascade="all, delete-orphan",
    )
