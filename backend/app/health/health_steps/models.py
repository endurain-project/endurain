from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from core.database import Base


class HealthSteps(Base):
    """
    SQLAlchemy model representing daily step count data for users.

    This model stores health and fitness tracking data related to the number of steps
    taken by a user on a specific date. It includes information about the data source
    and maintains a relationship with the User model.

    Attributes:
        id (int): Primary key, auto-incremented unique identifier for each record.
        user_id (int): Foreign key referencing users.id. Identifies the user who owns
            this health data. Cascades on delete and is indexed for performance.
        date (Date): The date for which the step count is recorded.
        steps (int): The total number of steps taken on the specified date.
        source (str, optional): The source or origin of the step data (e.g., fitness
            device, mobile app). Maximum length of 250 characters.
        user (relationship): SQLAlchemy relationship to the User model, enabling
            bidirectional access between users and their health step records.

    Table:
        health_steps

    Relationships:
        - Many-to-One with User model through user_id
    """

    __tablename__ = "health_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the health_steps belongs",
    )
    date = Column(
        Date,
        nullable=False,
        comment="Health steps date (date)",
    )
    steps = Column(
        Integer,
        nullable=False,
        comment="Number of steps taken",
    )
    source = Column(
        String(250),
        nullable=True,
        comment="Source of the health steps data",
    )

    # Define a relationship to the User model
    user = relationship("User", back_populates="health_steps")
