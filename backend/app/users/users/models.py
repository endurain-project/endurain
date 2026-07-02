"""User database models."""

from datetime import date as date_type
from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from activities.activity.models import Activity
    from auth.api_keys.models import UsersApiKeys
    from auth.credentials.models import LocalCredential
    from auth.identity_providers.link_tokens.models import IdpLinkToken
    from auth.identity_providers.links.models import IdentityLink
    from auth.mfa.backup_codes.models import MFABackupCode
    from auth.mfa.models import UsersMFA
    from auth.oauth_state.models import OAuthState
    from auth.password_reset_tokens.models import PasswordResetToken
    from auth.sessions.models import UsersSessions
    from auth.sign_up_tokens.models import SignUpToken
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
        health_fasting: List of health fasting records.
        health_water: List of health water intake records.
        health_poop: List of health poop records.
        notifications: List of notifications.
        goals: List of user goals.
        user_identity_providers: List of identity providers
            linked to the user.
        oauth_states: List of OAuth states for the user.
        mfa_backup_codes: List of MFA backup codes.
        auth_mfa: 1:1 MFA state row in ``users_mfa``
        idp_link_tokens: List of short-lived IdP link tokens for the user.
        local_credential: 1:1 local password credential row in
            ``users_local_credentials`` (``None`` for SSO-only accounts).
        mfa_enabled: Computed property — ``True`` when
            ``auth_mfa.mfa_enabled`` is set.
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

    # Relationships.
    #
    # ``passive_deletes=True`` pairs with the ON DELETE CASCADE
    # foreign keys these child tables declare. On user deletion the
    # database removes the children in a single statement instead of
    # SQLAlchemy loading and deleting every row in Python, which was
    # O(N) queries over activities, health rows, gear, and so on.
    users_sessions: Mapped[list["UsersSessions"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    password_reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sign_up_tokens: Mapped[list["SignUpToken"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    users_integrations: Mapped[list["UsersIntegrations"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    users_default_gear: Mapped[list["UsersDefaultGear"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    users_privacy_settings: Mapped[list["UsersPrivacySettings"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    gear: Mapped[list["Gear"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    gear_components: Mapped[list["GearComponents"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    activities: Mapped[list["Activity"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    followers: Mapped[list["Follower"]] = relationship(
        back_populates="following",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="Follower.following_id",
    )
    following: Mapped[list["Follower"]] = relationship(
        back_populates="follower",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="Follower.follower_id",
    )
    health_sleep: Mapped[list["HealthSleep"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    health_weight: Mapped[list["HealthWeight"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    health_steps: Mapped[list["HealthSteps"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    health_targets: Mapped[list["HealthTargets"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    health_fasting: Mapped[list["HealthFasting"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    health_water: Mapped[list["HealthWater"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    health_poop: Mapped[list["HealthPoop"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    goals: Mapped[list["UsersGoal"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    user_identity_providers: Mapped[list["IdentityLink"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    oauth_states: Mapped[list["OAuthState"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    mfa_backup_codes: Mapped[list["MFABackupCode"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    auth_mfa: Mapped["UsersMFA"] = relationship(
        back_populates="users",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    users_api_keys: Mapped[list["UsersApiKeys"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    idp_link_tokens: Mapped[list["IdpLinkToken"]] = relationship(
        back_populates="users",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    local_credential: Mapped["LocalCredential | None"] = relationship(
        back_populates="users",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def mfa_enabled(self) -> bool:
        """
        Return whether MFA is active for this user.

        Used by Pydantic schemas (``from_attributes=True``) and
        any caller that checks MFA status on the profile row.
        """
        return bool(self.auth_mfa and self.auth_mfa.mfa_enabled)
