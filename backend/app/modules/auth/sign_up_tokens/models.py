"""Sign-up token database models."""

from datetime import datetime as datetime_type

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class SignUpToken(Base):
    """Sign-up token database model.

    Attributes:
        id: Unique token identifier (string, 64 chars).
        user_id: ID of the user who owns the token.
        token_hash: Hashed sign-up token.
        created_at: Token creation date.
        expires_at: Token expiration date.
        used: Whether the token has been used.
        email: Email address the token proves (empty on rows from before the column existed).
        previous_email: Account email address when an email change was requested (email-change tokens only).
    """

    __tablename__ = "sign_up_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment=("User ID that the sign up token belongs to"),
    )
    token_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Hashed sign up token",
    )
    created_at: Mapped[datetime_type] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Token creation date (datetime)",
    )
    expires_at: Mapped[datetime_type] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Token expiration date (datetime)",
    )
    used: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Token usage status",
    )
    email: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Email address the token proves (empty on tokens issued before the column existed)",
    )
    previous_email: Mapped[str | None] = mapped_column(
        String(250),
        nullable=True,
        comment="Account email address when an email change was requested (email-change tokens only)",
    )
