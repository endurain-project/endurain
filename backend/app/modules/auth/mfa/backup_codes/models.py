"""SQLAlchemy ORM models for MFA backup codes."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.users.users.models import Users


class MFABackupCode(Base):
    """SQLAlchemy model for MFA backup codes.

    This model stores hashed backup codes that users can use as a fallback
    authentication method when their primary MFA device is unavailable.

    Attributes:
        id: Primary key, auto-incrementing identifier.
        user_id: Foreign key to the users table, identifies the code owner.
        code_hash: Argon2 hash of the backup code for secure storage.
        used: Flag indicating whether the code has been consumed.
        used_at: Timestamp when the code was used, if applicable.
        created_at: Timestamp when the code was generated (UTC).
        expires_at: Optional expiration timestamp for code rotation.

    Relationships:
        users: Many-to-one relationship with the Users model.

    Indexes:
        - Index on user_id for foreign key lookups.
        - Unique index on code_hash to prevent duplicates.
        - Index on used for filtering consumed codes.
        - Composite index (idx_user_unused_codes) on (user_id, used) for
          efficient lookups of available backup codes per user.
    """

    __tablename__ = "mfa_backup_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who owns this backup code",
    )
    code_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        comment="Argon2 hash of the backup code",
    )
    used: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="Whether this code has been consumed",
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When this code was used",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="When this code was generated",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Optional expiry for code rotation policy",
    )

    # Establish relationship back to Users model
    users: Mapped["Users"] = relationship(back_populates="mfa_backup_codes")

    # Composite index for fast unused code lookups
    __table_args__ = (Index("idx_user_unused_codes", "user_id", "used"),)
