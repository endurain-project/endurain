"""Auth-owned API key database models (table: ``users_api_keys``)."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.users.users.models import Users


class UsersApiKeys(Base):
    """
    User API key for third-party integrations.

    Attributes:
        id: Unique key identifier (UUID).
        user_id: Foreign key to users table.
        name: User-friendly label for the key.
        key_prefix: First 8 chars of the random part,
            shown in UI for identification.
        key_hash: SHA-256 hex digest of the full raw
            key. Never stored plaintext.
        scopes: JSON-encoded list of granted scopes.
        expires_at: Optional expiration timestamp.
            NULL means the key never expires.
        last_used_at: Timestamp of last successful
            authentication. Updated on each use.
        created_at: Key creation timestamp.
        is_active: Whether the key is active. Set to
            False to revoke without deleting.
        users: Relationship to Users model.
    """

    __tablename__ = "users_api_keys"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        nullable=False,
        comment="Unique key identifier (UUID4)",
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the API key belongs to",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="User-friendly label for the key",
    )
    key_prefix: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        comment=("First 8 chars of the random key part, used for UI identification"),
    )
    key_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="SHA-256 hex digest of the full raw key",
    )
    scopes: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="JSON-encoded list of granted scope strings",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Key expiration timestamp (NULL = no expiry)",
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last successful authentication",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Key creation timestamp",
    )
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        comment=("Whether the key is active. False = revoked (soft delete)"),
    )

    # Relationship to Users model
    users: Mapped["Users"] = relationship(back_populates="users_api_keys")
