"""Password reset token database models."""

from datetime import datetime as datetime_type
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.users.users.models import Users


class PasswordResetToken(Base):
    """
    Password reset token database model.

    Attributes:
        id: Unique token identifier (string, 64 chars).
        user_id: ID of the user who owns the token.
        token_hash: Hashed password reset token.
        created_at: Token creation date.
        expires_at: Token expiration date.
        used: Whether the token has been used.
        users: Relationship to the Users model.
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment=("User ID that the password reset token belongs to"),
    )
    token_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Hashed password reset token",
    )
    created_at: Mapped[datetime_type] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Token creation date (datetime)",
    )
    expires_at: Mapped[datetime_type] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Token expiration date (datetime)",
    )
    used: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Token usage status",
    )

    # Define a relationship to the Users model
    users: Mapped["Users"] = relationship(back_populates="password_reset_tokens")
