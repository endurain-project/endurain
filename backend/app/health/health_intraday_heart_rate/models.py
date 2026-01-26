from datetime import datetime
from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base


class HealthIntradayHeartrate(Base):
    """
    SQLAlchemy model representing intraday heart rate measurements data for users.

    This model stores health and fitness tracking data related to the heart rate measurements
    taken by a user at a specific time. It includes information about the data source
    and maintains a relationship with the User model.

    Attributes:
        id: Primary key, auto-incremented unique identifier.
        user_id: Foreign key referencing users.id.
        timestamp: Timestamp for which the step count is recorded.
        heart_rate: Heart rate measurement taken at a specific time.
        source: Source of the heart rate data (e.g., fitness device, app).
        user: Relationship to the User model.

    Table:
        health_intraday_heart_rate

    Relationships:
        - Many-to-One with User model through user_id
    """

    __tablename__ = "health_intraday_heart_rate"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the health_steps belongs",
    )
    timestamp: Mapped[datetime] = mapped_column(
        nullable=False,
        index=True,
        comment="Health intraday heart rates timestamp (datetime)",
    )
    heart_rate: Mapped[int] = mapped_column(
        nullable=False,
        comment="Heart rate measurment (bpm)",
    )
    source: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Source of the health heart rate data",
    )

    # Define a relationship to the User model
    # TODO: Change to Mapped["User"] when all modules use mapped
    user = relationship("Users", back_populates="health_intraday_heart_rate")
