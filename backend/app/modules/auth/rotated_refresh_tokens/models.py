"""Rotated refresh token database models for reuse detection."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class RotatedRefreshToken(Base):
    """Rotated refresh token for token reuse detection.

    Attributes:
        id: Primary key, a random UUID.
        token_family_id: UUID of the token family.
        hashed_token: Hashed old refresh token.
        client_fingerprint: SHA-256 hex of the rotating client's network and ``User-Agent``; an in-grace
            retry is answered only when it comes from the same client.
        rotation_count: Which rotation this token belonged to.
        rotated_at: When this token was rotated.
        expires_at: End of the replay grace window.
        refresh_token_exp: Expiry of the rotated refresh token; the record
            is kept until then, so a replay is recognised as reuse.
        replacement_refresh_token: Fernet-encrypted replacement
            refresh token replayed for in-grace retries.
        replacement_refresh_token_exp: Expiry of the
            replacement refresh token.
    """

    __tablename__ = "rotated_refresh_tokens"
    __table_args__ = (
        Index(
            "ix_rotated_refresh_tokens_expires_at_with_replacement",
            "expires_at",
            postgresql_where=text("replacement_refresh_token IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_family_id: Mapped[uuid.UUID] = mapped_column(
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
    client_fingerprint: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="SHA-256 hex of the rotating client's network and User-Agent, joined by a newline",
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
        comment="End of the replay grace window",
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
