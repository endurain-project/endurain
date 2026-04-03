from typing import TYPE_CHECKING
from datetime import datetime
from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, Text       
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, Mapped, mapped_column

from core.database import Base

if TYPE_CHECKING:
    from users.users.models import Users

class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that owns this route",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="Name of the route")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Description of the route")
    activity_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="Type of activity (e.g., cycling, running)")
    sub_type: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="Sub-type (e.g., gravel, road, trail)")

    distance: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, comment="Total distance in meters")
    elevation_gain: Mapped[float | None] = mapped_column(Float, nullable=True, default=0.0, comment="Total elevation gain in meters")

    route_data: Mapped[dict] = mapped_column(JSONB, nullable=False, comment="JSON structure containing waypoints and full coordinate path")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="When the route was created",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="When the route was last updated",
    )

    # Relationships
    user: Mapped["Users"] = relationship("Users", back_populates="routes")      


class RouteImportJob(Base):
    __tablename__ = "route_import_jobs"

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    route_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("routes.id", ondelete="SET NULL"),
        nullable=True,
        comment="ID of the created route, if successful",
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

