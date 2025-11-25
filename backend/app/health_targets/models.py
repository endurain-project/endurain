from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    DECIMAL,
)
from sqlalchemy.orm import relationship
from core.database import Base


class HealthTargets(Base):
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

    # Define a relationship to the User model
    user = relationship("User", back_populates="health_targets")
