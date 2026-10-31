"""Rotated refresh token database models for reuse detection."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class RotatedRefreshToken(Base):
    """Rotated refresh token for token reuse detection.

    Attributes:
        id: Primary key.
        token_family_id: UUID of the token family.
        hashed_token: Hashed old refresh token.
        rotation_count: Which rotation this token belonged to.
        rotated_at: When this token was rotated.
        expires_at: End of the replay grace window (rotated_at + 60 seconds).
        refresh_token_exp: Expiry of the rotated refresh token; the record
            is kept until then, so a replay is recognised as reuse.
        replacement_refresh_token: Fernet-encrypted replacement
            refresh token replayed for in-grace retries.
        replacement_refresh_token_exp: Expiry of the
            replacement refresh token.
    """

    __tablename__ = "rotated_refresh_tokens"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    token_family_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users_sessions.token_family_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="UUID of the token family",
    )
    hashed_token: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        comment="Hashed old refresh token",
    )
    rotation_count: Mapped[int] = mapped_column(
        nullable=False,
        comment="Which rotation this token belonged to",
    )
    rotated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When this token was rotated",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Cleanup marker (rotated_at + 60 seconds)",
    )
    refresh_token_exp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Expiry of the rotated refresh token; the record is purged after it",
    )
    replacement_refresh_token: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Fernet-encrypted replacement refresh token for idempotent in-grace replay",
    )
    replacement_refresh_token_exp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Expiry of the replacement refresh token",
    )
