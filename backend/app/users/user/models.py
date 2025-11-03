from sqlalchemy import Column, Integer, String, Date, Boolean
from sqlalchemy.orm import relationship
from core.database import Base

import followers.models as followers_models


# Data model for users table using SQLAlchemy's ORM
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(
        String(length=250),
        nullable=False,
        comment="User real name (May include spaces)",
    )
    username = Column(
        String(length=250),
        nullable=False,
        unique=True,
        index=True,
        comment="User username (letters, numbers, and dots allowed)",
    )
    email = Column(
        String(length=250),
        nullable=False,
        unique=True,
        index=True,
        comment="User email (max 250 characters)",
    )
    password = Column(
        String(length=250), nullable=False, comment="User password (hash)"
    )
    city = Column(String(length=250), nullable=True, comment="User city")
    birthdate = Column(Date, nullable=True, comment="User birthdate (date)")
    preferred_language = Column(
        String(length=5),
        nullable=False,
        comment="User preferred language (en, pt, others)",
    )
    gender = Column(
        Integer,
        nullable=False,
        default=1,
        comment="User gender (one digit)(1 - male, 2 - female, 3 - unspecified)",
    )
    units = Column(
        Integer,
        nullable=False,
        default=1,
        comment="User units (one digit)(1 - metric, 2 - imperial)",
    )
    height = Column(Integer, nullable=True, comment="User height in centimeters")
    max_heart_rate = Column(
        Integer, nullable=True, comment="User maximum heart rate (bpm)"
    )
    access_type = Column(
        Integer, nullable=False, comment="User type (one digit)(1 - user, 2 - admin)"
    )
    photo_path = Column(String(length=250), nullable=True, comment="User photo path")
    active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether the user is active (true - yes, false - no)",
    )
    first_day_of_week = Column(
        Integer,
        nullable=False,
        default=1,
        comment="User first day of week (0 - Sunday, 1 - Monday, etc.)",
    )
    currency = Column(
        Integer,
        nullable=False,
        default=1,
        comment="User currency (one digit)(1 - euro, 2 - dollar, 3 - pound)",
    )
    mfa_enabled = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether MFA is enabled for this user",
    )
    mfa_secret = Column(
        String(length=512),
        nullable=True,
        comment="User MFA secret for TOTP generation (encrypted at rest)",
    )
    email_verified = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether the user's email address has been verified (true - yes, false - no)",
    )
    pending_admin_approval = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether the user is pending admin approval for activation (true - yes, false - no)",
    )

    # Define a relationship to UsersSessions model
    users_sessions = relationship(
        "UsersSessions",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    # Define a relationship to PasswordResetToken model
    password_reset_tokens = relationship(
        "PasswordResetToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    # Define a relationship to SignUpToken model
    sign_up_tokens = relationship(
        "SignUpToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    # Define a relationship to UsersIntegrations model
    users_integrations = relationship(
        "UsersIntegrations",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    # Define a relationship to UsersDefaultGear model
    users_default_gear = relationship(
        "UsersDefaultGear",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    # Define a relationship to UsersPrivacySettings model
    users_privacy_settings = relationship(
        "UsersPrivacySettings",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    # Define a relationship to Gear model
    gear = relationship(
        "Gear",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    # Define a relationship to GearComponents model
    gear_components = relationship(
        "GearComponents",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    # Establish a one-to-many relationship with 'activities'
    activities = relationship(
        "Activity",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # Establish a one-to-many relationship between User and Followers
    followers = relationship(
        "Follower",
        back_populates="following",
        cascade="all, delete-orphan",
        foreign_keys=[followers_models.Follower.following_id],
    )

    # Establish a one-to-many relationship between User and Followers
    following = relationship(
        "Follower",
        back_populates="follower",
        cascade="all, delete-orphan",
        foreign_keys=[followers_models.Follower.follower_id],
    )

    # Establish a one-to-many relationship with 'health_data'
    health_data = relationship(
        "HealthData",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # Establish a one-to-many relationship with 'health_targets'
    health_targets = relationship(
        "HealthTargets",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # Establish a one-to-many relationship with 'notifications'
    notifications = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # Establish a one-to-many relationship with 'user_goals'
    goals = relationship(
        "UserGoal",
        back_populates="user",
        cascade="all, delete-orphan",
    )
