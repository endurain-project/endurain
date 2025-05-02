from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
)
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
    access_type = Column(
        Integer, nullable=False, comment="User type (one digit)(1 - user, 2 - admin)"
    )
    photo_path = Column(String(length=250), nullable=True, comment="User photo path")
    is_active = Column(
        Integer, nullable=False, comment="Is user active (1 - active, 2 - not active)"
    )
    default_activity_visibility = Column(
        Integer,
        nullable=False,
        default=0,
        comment="0 - public, 1 - followers, 2 - private",
    )

    # Define a relationship to UsersSessions model
    users_sessions = relationship(
        "UsersSessions",
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
    # Define a relationship to Gear model
    gear = relationship(
        "Gear",
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
