"""User database models."""

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Users(Base):
    """User account and profile information.

    Attributes:
        id: Primary key.
        name: User's real name (may include spaces).
        username: Unique username (letters, numbers, dots).
        email: Unique email address (max 250 characters).
        city: User's city.
        birthdate: User's birthdate.
        preferred_language: Preferred language code.
        gender: User's gender (male, female, unspecified).
        units: Measurement units (metric, imperial).
        height: User's height in centimeters.
        max_heart_rate: User maximum heart rate (bpm).
        access_type: User type (regular, admin).
        photo_path: Path to user's photo.
        active: Whether the user is active.
        first_day_of_week: First day of the week
            (sunday, monday, etc.).
        currency: Currency preference (euro, dollar, pound).
        email_verified: Whether the user's email address has
            been verified.
        pending_admin_approval: Whether the user is pending
            admin approval for activation.
        deactivated_at: When the account was deactivated by an
            administrator or by a deletion request, or None. A
            sign-up that is not yet verified or approved has none.
        deletion_requested_at: When the account was queued for
            deletion, or None.
        deletion_attempts: How many times the sweep queued the
            deletion again.
        health_sleep: List of health sleep records.
        health_weight: List of health weight records.
        health_steps: List of health steps records.
        health_targets: List of health targets.
        health_fasting: List of health fasting records.
        health_water: List of health water intake records.
        health_poop: List of health poop records.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    name: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        comment="User real name (May include spaces)",
    )
    username: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        unique=True,
        index=True,
        comment="User username (letters, numbers, and dots allowed)",
    )
    email: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        unique=True,
        index=True,
        comment="User email (max 250 characters)",
    )
    city: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="User city",
    )
    birthdate: Mapped[date_type | None] = mapped_column(
        nullable=True,
        comment="User birthdate (date)",
    )
    preferred_language: Mapped[str] = mapped_column(
        String(35),
        nullable=False,
        comment="User preferred BCP 47 language tag (en, pt-PT, zh-Hans, others)",
    )
    gender: Mapped[str] = mapped_column(
        String(20),
        default="male",
        nullable=False,
        comment="User gender (male, female, unspecified)",
    )
    units: Mapped[str] = mapped_column(
        String(20),
        default="metric",
        nullable=False,
        comment="User units (metric, imperial)",
    )
    height: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="User height in centimeters",
    )
    max_heart_rate: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="User maximum heart rate (bpm)",
    )
    access_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="User type (regular, admin)",
    )
    photo_path: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="User photo path",
    )
    active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        comment="Whether the user is active (true - yes, false - no)",
    )
    first_day_of_week: Mapped[str] = mapped_column(
        String(20),
        default="monday",
        nullable=False,
        comment="User first day of week (sunday, monday, etc.)",
    )
    currency: Mapped[str] = mapped_column(
        String(20),
        default="euro",
        nullable=False,
        comment="User currency (euro, dollar, pound)",
    )
    timezone: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment=("User IANA timezone, used as the fallback for activities with no GPS track"),
    )
    email_verified: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment=("Whether the user's email address has been verified (true - yes, false - no)"),
    )
    pending_admin_approval: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment=("Whether the user is pending admin approval for activation (true - yes, false - no)"),
    )

    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment=(
            "When the account was deactivated by an administrator or a deletion request; "
            "null for an active account and for a sign-up not yet verified or approved"
        ),
    )
    deletion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the account was queued for deletion; null for an account that is not being deleted",
    )
    deletion_attempts: Mapped[int] = mapped_column(
        nullable=False,
        server_default="0",
        default=0,
        comment="How many times the sweep queued this account's deletion again",
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
