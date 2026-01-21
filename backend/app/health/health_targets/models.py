from decimal import Decimal
from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base


class HealthTargets(Base):
    """
    User health targets configuration.

    Attributes:
        id: Primary key.
        user_id: Foreign key to users table (unique).
        weight: Target weight in kg.
        steps: Target daily steps count.
        sleep: Target sleep duration in seconds.
        user: Relationship to Users model.
    """

    __tablename__ = "health_targets"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="User ID that the health_target belongs",
    )
    weight: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=10, scale=2),
        nullable=True,
        comment="Weight in kg",
    )
    steps: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Number of steps taken",
    )
    sleep: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="Number of hours slept in seconds",
    )

    # Define a relationship to the Users model
    # TODO: Change to Mapped["User"] when all modules use mapped
    users = relationship("Users", back_populates="health_targets")
