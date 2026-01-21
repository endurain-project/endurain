"""Rotated refresh token database models for reuse detection."""

from datetime import datetime
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base


class RotatedRefreshToken(Base):
    """
    Rotated refresh token for token reuse detection.

    Attributes:
        id: Primary key.
        token_family_id: UUID of the token family.
        hashed_token: Hashed old refresh token.
        rotation_count: Which rotation this token belonged to.
        rotated_at: When this token was rotated.
        expires_at: Cleanup marker (rotated_at + 60 seconds).
        user_session: Relationship to UsersSessions model.
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
        nullable=False,
        comment="When this token was rotated",
    )
    expires_at: Mapped[datetime] = mapped_column(
        nullable=False,
        comment="Cleanup marker (rotated_at + 60 seconds)",
    )

    # Relationship to UsersSessions model
    # TODO: Change to Mapped["UsersSessions"] when all modules use mapped
    users_session = relationship(
        "UsersSessions",
        back_populates="rotated_refresh_tokens",
    )
