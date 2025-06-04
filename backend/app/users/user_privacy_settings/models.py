from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    Boolean,
)
from sqlalchemy.orm import relationship
from core.database import Base


class UsersPrivacySettings(Base):
    __tablename__ = "users_privacy_settings"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the privacy settings belongs",
    )
    default_activity_visibility = Column(
        Integer,
        nullable=False,
        default=0,
        comment="0 - public, 1 - followers, 2 - private",
    )
    hide_activity_start_time = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Hide activity start time",
    )
    hide_activity_location = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Hide activity location",
    )
    hide_activity_map = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Hide activity map",
    )
    hide_activity_hr = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Hide activity heart rate",
    )
    hide_activity_power = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Hide activity power",
    )
    hide_activity_cadence = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Hide activity cadence",
    )
    hide_activity_elevation = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Hide activity elevation",
    )
    hide_activity_speed = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Hide activity speed",
    )
    hide_activity_pace = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Hide activity pace",
    )
    hide_activity_laps = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Hide activity laps",
    )
    hide_activity_workout_sets_steps = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Hide activity workout sets and steps",
    )
    hide_activity_gear = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Hide activity gear",
    )


    # Define a relationship to the User model
    user = relationship("User", back_populates="users_privacy_settings")
