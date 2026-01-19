from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from core.database import Base


class MFABackupCode(Base):
    """
    SQLAlchemy model for MFA backup codes.

    This model stores hashed backup codes that users can use as a fallback
    authentication method when their primary MFA device is unavailable.

    Attributes:
        id (int): Primary key, auto-incrementing identifier.
        user_id (int): Foreign key to the users table, identifies the code owner.
        code_hash (str): Argon2 hash of the backup code for secure storage.
        used (bool): Flag indicating whether the code has been consumed.
        used_at (datetime): Timestamp when the code was used, if applicable.
        created_at (datetime): Timestamp when the code was generated (UTC).
        expires_at (datetime): Optional expiration timestamp for code rotation.

    Relationships:
        user: Many-to-one relationship with the Users model.

    Indexes:
        - Primary index on user_id for foreign key constraint
        - Unique index on code_hash to prevent duplicates
        - Index on used for filtering consumed codes
        - Composite index (idx_user_unused_codes) on user_id and used for
          efficient lookups of available backup codes per user
    """

    __tablename__ = "mfa_backup_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User who owns this backup code",
    )
    code_hash = Column(
        String(255),
        nullable=False,
        unique=True,
        comment="Argon2 hash of the backup code",
    )
    used = Column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="Whether this code has been consumed",
    )
    used_at = Column(DateTime, nullable=True, comment="When this code was used")
    created_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="When this code was generated",
    )
    expires_at = Column(
        DateTime, nullable=True, comment="Optional expiry for code rotation policy"
    )

    # Establish relationship back to Users model
    users = relationship("Users", back_populates="mfa_backup_codes")

    # Composite index for fast unused code lookups
    __table_args__ = (Index("idx_user_unused_codes", "user_id", "used"),)
