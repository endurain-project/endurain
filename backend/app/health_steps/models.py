from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    ForeignKey,
    DECIMAL,
)
from sqlalchemy.orm import relationship
from core.database import Base


class HealthSteps(Base):
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

    # Define a relationship to the User model
    user = relationship("User", back_populates="health_steps")
