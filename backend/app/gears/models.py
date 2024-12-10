from sqlalchemy import (
    Column,
    Integer,
    String,
    DATETIME,
    ForeignKey,
    DECIMAL,
)
from sqlalchemy.orm import relationship
from core.database import Base


# Data model for gear table using SQLAlchemy's ORM
class Gear(Base):
    __tablename__ = "gear"

    id = Column(Integer, primary_key=True)
    brand = Column(
        String(length=250), nullable=True, comment="Gear brand (May include spaces)"
    )
    model = Column(
        String(length=250), nullable=True, comment="Gear model (May include spaces)"
    )
    nickname = Column(
        String(length=250),
        unique=True,
        index=True,
        nullable=False,
        comment="Gear nickname (May include spaces)",
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
    created_at = Column(DATETIME, nullable=False, comment="Gear creation date (DATETIME)")
    is_active = Column(
        Integer, nullable=False, comment="Is gear active (0 - not active, 1 - active)"
    )
    initial_kms = Column(
        DECIMAL(precision=11, scale=3),
        nullable=False,
        default=0,
        comment="Initial kilometers of the gear",
    )
    strava_gear_id = Column(
        String(length=45), unique=True, nullable=True, comment="Strava gear ID"
    )
    garminconnect_gear_id = Column(
        String(length=45), unique=True, nullable=True, comment="Garmin Connect gear ID"
    )

    # Define a relationship to the User model
    user = relationship("User", back_populates="gear")
    # Establish a one-to-many relationship with 'activities'
    activities = relationship("Activity", back_populates="gear")
