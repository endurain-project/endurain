from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from core.database import Base

class Route(Base):
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that owns this route",
    )
    name = Column(String(255), nullable=False, comment="Name of the route")
    description = Column(Text, nullable=True, comment="Description of the route")
    activity_type = Column(String(50), nullable=False, comment="Type of activity (e.g., cycling, running)")
    sub_type = Column(String(50), nullable=True, comment="Sub-type (e.g., gravel, road, trail)")
    
    distance = Column(Float, nullable=False, default=0.0, comment="Total distance in meters")
    elevation_gain = Column(Float, nullable=True, default=0.0, comment="Total elevation gain in meters")
    
    route_data = Column(JSONB, nullable=False, comment="JSON structure containing waypoints and full coordinate path")
    
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When the route was created",
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="When the route was last updated",
    )

    # Relationships
    user = relationship("Users", back_populates="routes")
