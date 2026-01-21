from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    DECIMAL,
    BigInteger,
    Boolean,
    JSON,
)
from sqlalchemy.orm import relationship
from core.database import Base


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
    description = Column(
        String(length=2500),
        nullable=True,
        comment="Activity description (May include spaces)",
    )
    private_notes = Column(
        String(length=2500),
        nullable=True,
        comment="Activity private notes (May include spaces)",
    )
    distance = Column(Integer, nullable=False, comment="Distance in meters")
    activity_type = Column(
        Integer,
        nullable=False,
        comment="Gear type (1 - mountain bike, 2 - gravel bike, ...)",
    )
    start_time = Column(
        DateTime, nullable=False, comment="Activity start date (DATETIME)"
    )
    end_time = Column(DateTime, nullable=False, comment="Activity end date (DATETIME)")
    timezone = Column(
        String(length=250),
        nullable=True,
        comment="Activity timezone (May include spaces)",
    )
    total_elapsed_time = Column(
        DECIMAL(precision=20, scale=10),
        nullable=False,
        comment="Activity total elapsed time (s)",
    )
    total_timer_time = Column(
        DECIMAL(precision=20, scale=10),
        nullable=False,
        comment="Activity total timer time (s)",
    )
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
        DateTime, nullable=False, comment="Activity creation date (DATETIME)"
    )
    elevation_gain = Column(Integer, nullable=True, comment="Elevation gain in meters")
    elevation_loss = Column(Integer, nullable=True, comment="Elevation loss in meters")
    pace = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Pace seconds per meter (s/m)",
    )
    average_speed = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Average speed seconds per meter (s/m)",
    )
    max_speed = Column(
        DECIMAL(precision=20, scale=10),
        nullable=True,
        comment="Max speed seconds per meter (s/m)",
    )
    average_power = Column(Integer, nullable=True, comment="Average power (watts)")
    max_power = Column(Integer, nullable=True, comment="Max power (watts)")
    normalized_power = Column(
        Integer, nullable=True, comment="Normalized power (watts)"
    )
    average_hr = Column(Integer, nullable=True, comment="Average heart rate (bpm)")
    max_hr = Column(Integer, nullable=True, comment="Max heart rate (bpm)")
    average_cad = Column(Integer, nullable=True, comment="Average cadence (rpm)")
    max_cad = Column(Integer, nullable=True, comment="Max cadence (rpm)")
    workout_feeling = Column(
        Integer, nullable=True, comment="Workout feeling (0 to 100)"
    )
    workout_rpe = Column(Integer, nullable=True, comment="Workout RPE (10 to 100)")
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
    strava_gear_id = Column(String(length=45), nullable=True, comment="Strava gear ID")
    strava_activity_id = Column(
        BigInteger, unique=True, nullable=True, comment="Strava activity ID"
    )
    garminconnect_activity_id = Column(
        BigInteger, nullable=True, comment="Garmin Connect activity ID"
    )
    garminconnect_gear_id = Column(
        String(length=45), nullable=True, comment="Garmin Connect gear ID"
    )
    import_info = Column(
        JSON, default=None, nullable=True, doc="Additional import information"
    )
    is_hidden = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Indicates if the activity is hidden (e.g., duplicate activity waiting to be reviewed by the user)",
    )
    hide_start_time = Column(
        Boolean,
        nullable=False,
        comment="Hide activity start time",
    )
    hide_location = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Hide activity location",
    )
    hide_map = Column(
        Boolean,
        nullable=False,
        comment="Hide activity map",
    )
    hide_hr = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Hide activity heart rate",
    )
    hide_power = Column(
        Boolean,
        nullable=False,
        comment="Hide activity power",
    )
    hide_cadence = Column(
        Boolean,
        nullable=False,
        comment="Hide activity cadence",
    )
    hide_elevation = Column(
        Boolean,
        nullable=False,
        comment="Hide activity elevation",
    )
    hide_speed = Column(
        Boolean,
        nullable=False,
        comment="Hide activity speed",
    )
    hide_pace = Column(
        Boolean,
        nullable=False,
        comment="Hide activity pace",
    )
    hide_laps = Column(
        Boolean,
        nullable=False,
        comment="Hide activity laps",
    )
    hide_workout_sets_steps = Column(
        Boolean,
        nullable=False,
        comment="Hide activity workout sets and steps",
    )
    hide_gear = Column(
        Boolean,
        nullable=False,
        comment="Hide activity gear",
    )
    tracker_manufacturer = Column(
        String(length=250),
        nullable=True,
        comment="Tracker manufacturer (e.g., Garmin, Suunto, Polar)",
    )
    tracker_model = Column(
        String(length=250),
        nullable=True,
        comment="Tracker model (e.g., Forerunner 245, Ambit3 Peak, Vantage V2)",
    )

    # Define a relationship to the Users model
    users = relationship("Users", back_populates="activities")

    # Define a relationship to the Gear model
    gear = relationship("Gear", back_populates="activities")

    # Establish a one-to-many relationship with 'activity_laps'
    activity_laps = relationship(
        "ActivityLaps",
        back_populates="activity",
        cascade="all, delete-orphan",
    )

    # Establish a one-to-many relationship with 'activity_sets'
    activity_sets = relationship(
        "ActivitySets",
        back_populates="activity",
        cascade="all, delete-orphan",
    )

    # Establish a one-to-many relationship with 'activities_streams'
    activities_streams = relationship(
        "ActivityStreams",
        back_populates="activity",
        cascade="all, delete-orphan",
    )

    # Establish a one-to-many relationship with 'activity_workout_steps'
    activity_workout_steps = relationship(
        "ActivityWorkoutSteps",
        back_populates="activity",
        cascade="all, delete-orphan",
    )

    # Establish a one-to-many relationship with 'activity_media'
    activity_media = relationship(
        "ActivityMedia",
        back_populates="activity",
        cascade="all, delete-orphan",
    )
