from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    DECIMAL,
)
from sqlalchemy.orm import relationship
from core.database import Base


class HealthTargets(Base):
    """
    SQLAlchemy model representing health targets for users.

    This table stores health-related goals and targets for individual users,
    including weight, daily steps, and sleep duration objectives.

    Attributes:
        id (int): Primary key, auto-incremented unique identifier for the health target.
        user_id (int): Foreign key referencing users.id. Each user can have only one
            set of health targets (unique constraint). Cascades on delete.
        weight (Decimal): Target weight in kilograms with precision of 10 digits
            and 2 decimal places. Optional field.
        steps (int): Target number of daily steps. Optional field.
        sleep (int): Target sleep duration in seconds. Optional field.
        user (relationship): SQLAlchemy relationship to the User model, establishing
            a bidirectional link via the 'health_targets' back_populates attribute.

    Relationships:
        - One-to-one relationship with User model (enforced by unique constraint on user_id)

    Indexes:
        - user_id: Indexed for efficient lookups
    """

    __tablename__ = "health_targets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="User ID that the health_target belongs",
    )
    weight = Column(
        DECIMAL(precision=10, scale=2),
        nullable=True,
        comment="Weight in kg",
    )
    steps = Column(
        Integer,
        nullable=True,
        comment="Number of steps taken",
    )
    sleep = Column(
        Integer,
        nullable=True,
        comment="Number of hours slept in seconds",
    )

    # Define a relationship to the User model
    user = relationship("User", back_populates="health_targets")
