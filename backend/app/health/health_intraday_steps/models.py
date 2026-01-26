from datetime import datetime
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base


class HealthIntradaySteps(Base):
    """
    SQLAlchemy model representing intraday step counts data for users.

    This model stores health and fitness tracking data related to the cumulative number of steps
    taken by a user at a specific time. It includes information about the data source
    and maintains a relationship with the User model. Steps are typically tracked separately
    per activity type.

    Attributes:
        id: Primary key, auto-incremented unique identifier.
        user_id: Foreign key referencing users.id.
        timestamp: Timestamp for which the step count is recorded.
        steps: Cumulative number of steps at that time for a given day.
        distance: Cumulative distance traveled at that time for a given day.
        source: Source of the step data (e.g., fitness device, app).
        user: Relationship to the User model.
        activity_type: Activity type associated with these steps.
        intensity: Intensity.

    Table:
        health_intraday_steps

    Relationships:
        - Many-to-One with User model through user_id
    """

    __tablename__ = "health_intraday_steps"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the health_intraday_steps belongs",
    )
    timestamp: Mapped[datetime] = mapped_column(
        nullable=False,
        index=True,
        comment="Health intraday steps timestamp (datetime)",
    )
    steps: Mapped[int] = mapped_column(
        nullable=False,
        comment="Cumulative number of steps taken",
    )
    distance: Mapped[float] = mapped_column(
        nullable=True,
        comment="Cumulative distance traveled",
    )
    source: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Source of the health steps data",
    )
    activity_type: Mapped[int] = mapped_column(
        nullable=True,
        comment="Activity type",
    )
    intensity: Mapped[int] = mapped_column(
        nullable=True,
        comment="Intensity",
    )
    # Define a relationship to the User model
    # TODO: Change to Mapped["User"] when all modules use mapped
    user = relationship("User", back_populates="health_intraday_steps")
