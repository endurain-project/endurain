"""SQLAlchemy ORM model for health steps records."""

from datetime import date as date_type

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class HealthSteps(Base):
    """SQLAlchemy model representing daily step count data for users.

    This model stores health and fitness tracking data related to the number of steps
    taken by a user on a specific date. It includes information about the data source
    and belongs to a user through ``user_id``.

    Attributes:
        id: Primary key, auto-incremented unique identifier.
        user_id: Foreign key referencing users.id.
        date: Calendar date for which the step count is recorded.
        steps: Total number of steps taken on the date.
        source: Source of the step data (e.g., fitness device, app).

    Table:
        health_steps
    """

    __tablename__ = "health_steps"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_health_steps_user_date"),)

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
    date: Mapped[date_type] = mapped_column(
        nullable=False,
        index=True,
        comment="Health steps date (date)",
    )
    steps: Mapped[int] = mapped_column(
        nullable=False,
        comment="Number of steps taken",
    )
    source: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Source of the health steps data",
    )

    version: Mapped[int] = mapped_column(
        nullable=False,
        server_default="1",
        default=1,
        comment="Optimistic-concurrency counter, surfaced to clients as the ETag",
    )

    # SQLAlchemy bumps ``version`` on each ORM flush and adds it to the UPDATE's
    # WHERE clause, raising StaleDataError when the row moved underneath.
    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012
