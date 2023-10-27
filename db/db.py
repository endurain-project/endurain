import os
import urllib.parse  # Import urllib.parse for URL encoding
import logging
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine, Column, Integer, String, Date, DateTime, ForeignKey, LargeBinary, DECIMAL
from dotenv import load_dotenv
from datetime import datetime
from sqlalchemy.dialects.mysql import JSON

# Load the environment variables from config/.env
load_dotenv('config/.env')

logger = logging.getLogger("myLogger")

# Define the database connection URL using environment variables
#db_url = f"mysql+mysqlconnector://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_DATABASE')}"
db_password = urllib.parse.quote_plus(os.getenv('DB_PASSWORD'))
db_url = f"mysql://{os.getenv('DB_USER')}:{db_password}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_DATABASE')}"

# Create the SQLAlchemy engine
engine = create_engine(db_url, pool_size=10, max_overflow=20, pool_timeout=180)

# Create a session factory
Session = sessionmaker(bind=engine)

# Create a base class for declarative models
Base = declarative_base()

# Data model for users table using SQLAlchemy's ORM
class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    name = Column(String(length=45), nullable=False, comment='User real name (May include spaces)')
    username = Column(String(length=45), nullable=False, unique=True, comment='User username (letters, numbers, and dots allowed)')
    email = Column(String(length=250), nullable=False, unique=True, comment='User email (max 45 characters)')
    password = Column(String(length=100), nullable=False, comment='User password (hash)')
    city = Column(String(length=45), nullable=True, comment='User city')
    birthdate = Column(Date, nullable=True, comment='User birthdate (date)')
    preferred_language = Column(String(length=5), nullable=False, comment='User preferred language (en, pt, others)')
    gender = Column(Integer, nullable=False, comment='User gender (one digit)(1 - male, 2 - female)')
    access_type = Column(Integer, nullable=False, comment='User type (one digit)(1 - student, 2 - admin, 3 - teacher, 4 - parent)')
    photo_path = Column(String(length=250), nullable=True, comment='User photo path')
    photo_path_aux = Column(String(length=250), nullable=True, comment='Auxiliary photo path')
    is_active = Column(Integer, nullable=False, comment='Is user active (0 - not active, 1 - active)')
    strava_token = Column(String(length=250), nullable=True)
    strava_refresh_token = Column(String(length=250), nullable=True)
    strava_token_expires_at = Column(DateTime, nullable=True)

    # Define a relationship to AccessToken model
    access_tokens = relationship('AccessToken', back_populates='user')
    # Define a relationship to Gear model
    gear = relationship('Gear', back_populates='user')
    # Establish a one-to-many relationship with 'activities'
    activities = relationship('Activity', back_populates='user')

# Data model for access_tokens table using SQLAlchemy's ORM
class AccessToken(Base):
    __tablename__ = 'access_tokens'

    id = Column(Integer, primary_key=True)
    token = Column(String(length=256), nullable=False, comment='User token')
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, comment='User ID that the token belongs')
    created_at = Column(DateTime, nullable=False, comment='Token creation date (date)')
    expires_at = Column(DateTime, nullable=False, comment='Token expiration date (date)')

    # Define a relationship to the User model
    user = relationship('User', back_populates='access_tokens')

# Data model for gear table using SQLAlchemy's ORM
class Gear(Base):
    __tablename__ = 'gear'

    id = Column(Integer, primary_key=True)
    brand = Column(String(length=45), nullable=True, comment='Gear brand (May include spaces)')
    model = Column(String(length=45), nullable=True, comment='Gear model (May include spaces)')
    nickname = Column(String(length=45), nullable=False, comment='Gear nickname (May include spaces)')
    gear_type = Column(Integer, nullable=False, comment='Gear type (1 - bike, 2 - shoes, 3 - wetsuit)')
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, comment='User ID that the gear belongs to')
    created_at = Column(DateTime, nullable=False, comment='Gear creation date (date)')
    is_active = Column(Integer, nullable=False, comment='Is gear active (0 - not active, 1 - active)')

    # Define a relationship to the User model
    user = relationship('User', back_populates='gear')

# Data model for activities table using SQLAlchemy's ORM
class Activity(Base):
    __tablename__ = 'activities'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, comment='User ID that the activity belongs')
    name = Column(String(length=45), nullable=True, comment='Activity name (May include spaces)')
    distance = Column(Integer, nullable=False, comment='Distance in meters')
    activity_type = Column(Integer, nullable=False, comment='Gear type (1 - mountain bike, 2 - gravel bike, ...)')
    start_time = Column(DateTime, nullable=False, comment='Activity start date (datetime)')
    end_time = Column(DateTime, nullable=False, comment='Activity end date (datetime)')
    city = Column(String(length=45), nullable=True, comment='Activity city (May include spaces)')
    town = Column(String(length=45), nullable=True, comment='Activity town (May include spaces)')
    country = Column(String(length=45), nullable=True, comment='Activity country (May include spaces)')
    created_at = Column(DateTime, nullable=False, comment='Activity creation date (datetime)')
    waypoints = Column(JSON, nullable=True, doc='Store waypoints data')

    # Define a relationship to the User model
    user = relationship('User', back_populates='activities')

    # Establish a one-to-many relationship with 'waypoints'
    #waypoints = relationship('Waypoint', back_populates='activity')

# Data model for waypoints table using SQLAlchemy's ORM
# class Waypoint(Base):
#     __tablename__ = 'waypoints'

#     id = Column(Integer, primary_key=True, autoincrement=True)
#     activity_id = Column(Integer, ForeignKey('activities.id'), nullable=False, comment='Activity ID that the waypoint belongs')
#     latitude = Column(DECIMAL(precision=10, scale=6), nullable=True, comment='Latitude with 6 decimal places')
#     longitude = Column(DECIMAL(precision=10, scale=6), nullable=True, comment='Longitude with 6 decimal places')
#     elevation = Column(DECIMAL(precision=8, scale=2), nullable=True, comment='Elevation with 2 decimal places')
#     time = Column(DateTime, nullable=True, comment='Timestamp of the waypoint')
#     heart_rate = Column(Integer, nullable=True, comment='Heart rate data')
#     cadence = Column(Integer, nullable=True, comment='Cadence data')
#     power = Column(Integer, nullable=True, comment='Power data')

#     # Define a relationship to the Activity model
#     activity = relationship('Activity', back_populates='waypoints')

# Context manager to get a database session
from contextlib import contextmanager

@contextmanager
def get_db_session():
    session = Session()
    try:
        yield session
    finally:
        session.close()
