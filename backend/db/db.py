"""
Module: db.py

This module defines the SQLAlchemy data models and database logic for managing users, followers,
access tokens, gear, and activities. It establishes the database connection, creates tables,
and provides a context manager for handling database sessions.

Classes:
- Follower
- User
- AccessToken
- Gear
- Activity

Functions:
- create_database_tables: Creates the necessary database tables.
- get_db_session: Context manager for obtaining a database session.

Usage:
1. Import this module: `from my_database_logic import create_database_tables, get_db_session`
2. Create tables: `create_database_tables()`
3. Use the context manager for database sessions: 
    with get_db_session() as session:
    # Perform database operations using the session
Note: Ensure that environment variables for database configuration are properly set before using
this module.
"""
import os
import logging
import hashlib
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import (
    create_engine,
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
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.engine.url import URL
from contextlib import contextmanager
from sqlalchemy.orm.exc import NoResultFound

logger = logging.getLogger("myLogger")

# Define the database connection URL using environment variables
db_url = URL.create(
    drivername="mysql",
    username=os.environ.get("DB_USER"),
    password=os.environ.get("DB_PASSWORD"),
    host=os.environ.get("DB_HOST"),
    port=os.environ.get("DB_PORT"),
    database=os.environ.get("DB_DATABASE"),
)

# Create the SQLAlchemy engine
engine = create_engine(
    db_url, pool_size=10, max_overflow=20, pool_timeout=180, pool_recycle=3600
)

# Create a session factory
Session = sessionmaker(bind=engine)

# Create a base class for declarative models
Base = declarative_base()


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
        Integer, nullable=False, comment="User type (one digit)(1 - student, 2 - admin)"
    )
    photo_path = Column(String(length=250), nullable=True, comment="User photo path")
    photo_path_aux = Column(
        String(length=250), nullable=True, comment="Auxiliary photo path"
    )
    is_active = Column(
        Integer, nullable=False, comment="Is user active (2 - not active, 1 - active)"
    )
    strava_state = Column(String(length=45), nullable=True)
    strava_token = Column(String(length=250), nullable=True)
    strava_refresh_token = Column(String(length=250), nullable=True)
    strava_token_expires_at = Column(DateTime, nullable=True)

    # Define a relationship to AccessToken model
    access_tokens = relationship("AccessToken", back_populates="user")
    # Define a relationship to Gear model
    gear = relationship("Gear", back_populates="user")
    # Establish a one-to-many relationship with 'activities'
    activities = relationship("Activity", back_populates="user")
    # Establish a one-to-many relationship between User and UserSettings
    # user_settings = relationship("UserSettings", back_populates="user")

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

    # Define a relationship to the User model
    user = relationship("User", back_populates="gear")
    # Establish a one-to-many relationship with 'activities'
    activities = relationship("Activity", back_populates="gear")
    # Establish a one-to-many relationship between Gear and UserSettings


#   user_settings = relationship("UserSettings", back_populates="gear")

# class UserSettings(Base):
#    __tablename__ = 'user_settings'

#    id = Column(Integer, primary_key=True, autoincrement=True)
#    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, doc='User ID that the activity belongs')
#    activity_type = Column(Integer, nullable=True, doc='Gear type')
#    gear_id = Column(Integer, ForeignKey('gear.id'), nullable=True, doc='Gear ID associated with this activity')

#    # Define the foreign key relationships
#    user = relationship("User", back_populates="user_settings")
#    gear = relationship("Gear", back_populates="user_settings")


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
    waypoints = Column(JSON, nullable=True, doc="Store waypoints data")
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
    strava_activity_id = Column(BigInteger, nullable=True, comment="Strava activity ID")

    # Define a relationship to the User model
    user = relationship("User", back_populates="activities")

    # Define a relationship to the Gear model
    gear = relationship("Gear", back_populates="activities")


def create_database_tables():
    # Create tables
    Base.metadata.create_all(bind=engine)

    # Create a user and add it to the database
    with get_db_session() as session:
        try:
            # Check if the user already exists
            session.query(User).filter_by(username="admin").one()
            print("Admin user already exists. Will skip user creation.")
        except NoResultFound:
            # Create a new SHA-256 hash object
            sha256_hash = hashlib.sha256()

            # Update the hash object with the bytes of the input string
            sha256_hash.update("admin".encode('utf-8'))

            # Get the hexadecimal representation of the hash
            hashed_string = sha256_hash.hexdigest()

            # If the user doesn't exist, create a new user
            new_user = User(
                name="Administrator",
                username="admin",
                email="admin@example.com",
                password=hashed_string,
                preferred_language="en",
                gender=1,
                access_type=2,
                is_active=1,
            )

            # Add the new user to the session
            session.add(new_user)
            session.commit()

            print("Admin user created successfully.")


@contextmanager
def get_db_session():
    session = Session()
    try:
        yield session
    finally:
        session.close()
