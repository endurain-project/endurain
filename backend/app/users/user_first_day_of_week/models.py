from typing import Optional
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from pydantic import BaseModel, Field


SQLAlchemyBase = declarative_base()

class User(SQLAlchemyBase):
    __tablename__ = "users"
    
   
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    city = Column(String, nullable=True)
    birthdate = Column(DateTime, nullable=True)
    preferred_language = Column(String, default="en")
    gender = Column(String, nullable=True)
    units = Column(String, nullable=True)
    height = Column(Integer, nullable=True)
    access_type = Column(String, nullable=True)
    photo_path = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    is_strava_linked = Column(Boolean, default=False)
    is_garminconnect_linked = Column(Boolean, default=False)
    default_activity_visibility = Column(Integer, default=0)
    hide_activity_start_time = Column(Boolean, default=False)
    hide_activity_location = Column(Boolean, default=False)
    hide_activity_map = Column(Boolean, default=False)
    hide_activity_hr = Column(Boolean, default=False)
    hide_activity_power = Column(Boolean, default=False)
    hide_activity_cadence = Column(Boolean, default=False)
    hide_activity_elevation = Column(Boolean, default=False)
    hide_activity_speed = Column(Boolean, default=False)
    hide_activity_pace = Column(Boolean, default=False)
    hide_activity_laps = Column(Boolean, default=False)
    hide_activity_workout_sets_steps = Column(Boolean, default=False)
    hide_activity_gear = Column(Boolean, default=False)
    
    # New field for first day of week preference
    first_day_of_week = Column(
        Integer,
        default=0,
        nullable=False,
        doc="First day of week preference: 0=Sunday, 1=Monday, 2=Tuesday, 3=Wednesday, 4=Thursday, 5=Friday, 6=Saturday"
    )

class UserCreate(BaseModel):
    name: str
    username: str
    email: str
    city: Optional[str] = None
    birthdate: Optional[str] = None
    preferred_language: str = "en"
    gender: Optional[str] = None
    units: Optional[str] = None
    height: Optional[int] = None
    access_type: Optional[str] = None
    photo_path: Optional[str] = None
    is_active: bool = True
    is_strava_linked: bool = False
    is_garminconnect_linked: bool = False
    default_activity_visibility: int = 0
    hide_activity_start_time: bool = False
    hide_activity_location: bool = False
    hide_activity_map: bool = False
    hide_activity_hr: bool = False
    hide_activity_power: bool = False
    hide_activity_cadence: bool = False
    hide_activity_elevation: bool = False
    hide_activity_speed: bool = False
    hide_activity_pace: bool = False
    hide_activity_laps: bool = False
    hide_activity_workout_sets_steps: bool = False
    hide_activity_gear: bool = False
    
    first_day_of_week: Optional[int] = Field(
        default=0,
        ge=0,
        le=6,
        description="First day of week preference: 0=Sunday, 1=Monday, 2=Tuesday, 3=Wednesday, 4=Thursday, 5=Friday, 6=Saturday"
    )

class UserUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    city: Optional[str] = None
    birthdate: Optional[str] = None
    preferred_language: Optional[str] = None
    gender: Optional[str] = None
    units: Optional[str] = None
    height: Optional[int] = None
    access_type: Optional[str] = None
    photo_path: Optional[str] = None
    is_active: Optional[bool] = None
    is_strava_linked: Optional[bool] = None
    is_garminconnect_linked: Optional[bool] = None
    default_activity_visibility: Optional[int] = None
    hide_activity_start_time: Optional[bool] = None
    hide_activity_location: Optional[bool] = None
    hide_activity_map: Optional[bool] = None
    hide_activity_hr: Optional[bool] = None
    hide_activity_power: Optional[bool] = None
    hide_activity_cadence: Optional[bool] = None
    hide_activity_elevation: Optional[bool] = None
    hide_activity_speed: Optional[bool] = None
    hide_activity_pace: Optional[bool] = None
    hide_activity_laps: Optional[bool] = None
    hide_activity_workout_sets_steps: Optional[bool] = None
    hide_activity_gear: Optional[bool] = None
    
    first_day_of_week: Optional[int] = Field(
        None,
        ge=0,
        le=6,
        description="First day of week preference: 0=Sunday, 1=Monday, 2=Tuesday, 3=Wednesday, 4=Thursday, 5=Friday, 6=Saturday"
    )

class UserRead(BaseModel):
    id: int
    name: str
    username: str
    email: str
    city: Optional[str] = None
    birthdate: Optional[str] = None
    preferred_language: str
    gender: Optional[str] = None
    units: Optional[str] = None
    height: Optional[int] = None
    access_type: Optional[str] = None
    photo_path: Optional[str] = None
    is_active: bool
    is_strava_linked: bool
    is_garminconnect_linked: bool
    default_activity_visibility: int
    hide_activity_start_time: bool
    hide_activity_location: bool
    hide_activity_map: bool
    hide_activity_hr: bool
    hide_activity_power: bool
    hide_activity_cadence: bool
    hide_activity_elevation: bool
    hide_activity_speed: bool
    hide_activity_pace: bool
    hide_activity_laps: bool
    hide_activity_workout_sets_steps: bool
    hide_activity_gear: bool
    
    first_day_of_week: Optional[int] = Field(
        default=0,
        ge=0,
        le=6,
        description="First day of week preference: 0=Sunday, 1=Monday, 2=Tuesday, 3=Wednesday, 4=Thursday, 5=Friday, 6=Saturday"
    )

    class Config:
        from_attributes = True  