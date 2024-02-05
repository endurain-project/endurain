from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    ForeignKey,
    DECIMAL,
    BigInteger,
    Boolean,
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.mysql import JSON
from database import Base

# Data model for followers table using SQLAlchemy's ORM
class Follower(Base):
    __tablename__ = "followers"

    follower_id = Column(
        Integer,
        ForeignKey("users.id"),
        primary_key=True,
        index=True,
        comment="ID of the follower user",
    )
    following_id = Column(
        Integer,
        ForeignKey("users.id"),
        primary_key=True,
        index=True,
        comment="ID of the following user",
    )
    is_accepted = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether the follow request is accepted or not",
    )

    # Define a relationship to the User model
    follower = relationship(
        "User", foreign_keys=[follower_id], back_populates="followers"
    )
    # Define a relationship to the User model
    following = relationship(
        "User", foreign_keys=[following_id], back_populates="following"
    )


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
        String(length=100), nullable=False, comment="User password (hash)"
    )
    city = Column(String(length=250), nullable=True, comment="User city")
    birthdate = Column(Date, nullable=True, comment="User birthdate (date)")
    preferred_language = Column(
        String(length=5),
        nullable=False,
        comment="User preferred language (en, pt, others)",
    )
    gender = Column(
        Integer, nullable=False, comment="User gender (one digit)(1 - male, 2 - female)"
    )
    access_type = Column(
        Integer, nullable=False, comment="User type (one digit)(1 - user, 2 - admin)"
    )
    photo_path = Column(String(length=250), nullable=True, comment="User photo path")
    photo_path_aux = Column(
        String(length=250), nullable=True, comment="Auxiliary photo path"
    )
    is_active = Column(
        Integer, nullable=False, comment="Is user active (2 - not active, 1 - active)"
    )

    # Define a relationship to UserIntegrations model
    users_integrations = relationship(
        "UserIntegrations",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    # Define a relationship to AccessToken model
    access_tokens = relationship(
        "AccessToken",
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
        foreign_keys=[Follower.following_id],
    )
    # Establish a one-to-many relationship between User and Followers
    following = relationship(
        "Follower",
        back_populates="follower",
        cascade="all, delete-orphan",
        foreign_keys=[Follower.follower_id],
    )


class UserIntegrations(Base):
    __tablename__ = "users_integrations"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the token belongs",
    )
    strava_state = Column(String(length=45), nullable=True)
    strava_token = Column(String(length=250), nullable=True)
    strava_refresh_token = Column(String(length=250), nullable=True)
    strava_token_expires_at = Column(DateTime, nullable=True)
    strava_sync_gear = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether Strava gear is to be synced",
    )

    # Define a relationship to the User model
    user = relationship("User", back_populates="users_integrations")


# Data model for access_tokens table using SQLAlchemy's ORM
class AccessToken(Base):
    __tablename__ = "access_tokens"

    id = Column(Integer, primary_key=True)
    token = Column(String(length=256), nullable=False, comment="User token")
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the token belongs",
    )
    created_at = Column(DateTime, nullable=False, comment="Token creation date (date)")
    expires_at = Column(
        DateTime, nullable=False, comment="Token expiration date (date)"
    )

    # Define a relationship to the User model
    user = relationship("User", back_populates="access_tokens")


# Data model for gear table using SQLAlchemy's ORM
class Gear(Base):
    __tablename__ = "gear"

    id = Column(Integer, primary_key=True)
    brand = Column(
        String(length=45), nullable=True, comment="Gear brand (May include spaces)"
    )
    model = Column(
        String(length=45), nullable=True, comment="Gear model (May include spaces)"
    )
    nickname = Column(
        String(length=45), nullable=False, comment="Gear nickname (May include spaces)"
    )
    gear_type = Column(
        Integer, nullable=False, comment="Gear type (1 - bike, 2 - shoes, 3 - wetsuit)"
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="User ID that the gear belongs to",
    )
    created_at = Column(DateTime, nullable=False, comment="Gear creation date (date)")
    is_active = Column(
        Integer, nullable=False, comment="Is gear active (0 - not active, 1 - active)"
    )
    strava_gear_id = Column(BigInteger, nullable=True, comment="Strava gear ID")

    # Define a relationship to the User model
    user = relationship("User", back_populates="gear")
    # Establish a one-to-many relationship with 'activities'
    activities = relationship("Activity", back_populates="gear")


# Data model for activities table using SQLAlchemy's ORM
class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the activity belongs",
    )
    name = Column(
        String(length=250), nullable=True, comment="Activity name (May include spaces)"
    )
    distance = Column(Integer, nullable=False, comment="Distance in meters")
    activity_type = Column(
        Integer,
        nullable=False,
        comment="Gear type (1 - mountain bike, 2 - gravel bike, ...)",
    )
    start_time = Column(
        DateTime, nullable=False, comment="Activity start date (datetime)"
    )
    end_time = Column(DateTime, nullable=False, comment="Activity end date (datetime)")
    city = Column(
        String(length=250), nullable=True, comment="Activity city (May include spaces)"
    )
    town = Column(
        String(length=250), nullable=True, comment="Activity town (May include spaces)"
    )
    country = Column(
        String(length=250),
        nullable=True,
        comment="Activity country (May include spaces)",
    )
    created_at = Column(
        DateTime, nullable=False, comment="Activity creation date (datetime)"
    )
    elevation_gain = Column(Integer, nullable=False, comment="Elevation gain in meters")
    elevation_loss = Column(Integer, nullable=False, comment="Elevation loss in meters")
    pace = Column(
        DECIMAL(precision=20, scale=10),
        nullable=False,
        comment="Pace seconds per meter (s/m)",
    )
    average_speed = Column(
        DECIMAL(precision=20, scale=10),
        nullable=False,
        comment="Average speed seconds per meter (s/m)",
    )
    average_power = Column(Integer, nullable=False, comment="Average power (watts)")
    calories = Column(
        Integer,
        nullable=True,
        comment="The number of kilocalories consumed during this activity",
    )
    visibility = Column(
        Integer,
        nullable=False,
        default=0,
        comment="0 - public, 1 - followers, 2 - private",
    )
    gear_id = Column(
        Integer,
        ForeignKey("gear.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Gear ID associated with this activity",
    )
    strava_gear_id = Column(BigInteger, nullable=True, comment="Strava gear ID")
    strava_activity_id = Column(BigInteger, nullable=True, comment="Strava activity ID")

    # Define a relationship to the User model
    user = relationship("User", back_populates="activities")

    # Define a relationship to the Gear model
    gear = relationship("Gear", back_populates="activities")

    # Establish a one-to-many relationship with 'activities_streams'
    activities_streams = relationship(
        "ActivityStreams",
        back_populates="activity",
        cascade="all, delete-orphan",
    )


class ActivityStreams(Base):
    __tablename__ = "activities_streams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    activity_id = Column(
        Integer,
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Activity ID that the activity stream belongs",
    )
    stream_type = Column(
        Integer,
        nullable=False,
        comment="Stream type (1 - HR, 2 - Power, 3 - Cadence, 4 - Elevation, 5 - Velocity, 6 - Pace, 7 - lat/lon)",
    )
    stream_waypoints = Column(JSON, nullable=False, doc="Store waypoints data")
    strava_activity_stream_id = Column(
        BigInteger, nullable=True, comment="Strava activity stream ID"
    )

    # Define a relationship to the User model
    activity = relationship("Activity", back_populates="activities_streams")