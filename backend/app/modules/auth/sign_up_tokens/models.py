"""Sign-up token database models."""

import uuid
from datetime import datetime as datetime_type

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class SignUpToken(Base):
    """Sign-up token database model.

    Attributes:
        id: Unique token identifier (a random UUID).
        user_id: ID of the user who owns the token.
        token_hash: Hashed sign-up token.
        created_at: Token creation date.
        expires_at: Token expiration date.
        used: Whether the token has been used.
        email: Email address the token proves (empty on rows from before the column existed).
        previous_email: Account email address when an email change was requested (email-change tokens only).
        security_generation: Account security generation the email change was requested under (email-change
            tokens only); the confirmation is refused once the account's generation has moved on.
        change_id: Identifier of the email change the row belongs to (email-change tokens only): the id of the row
            created when it was requested, copied to the rows that re-issue its confirmation link. The "this
            wasn't me" link names it.
        revert_until: End of the change's revert window (email-change tokens only); the row is kept until then.
        confirmed_at: When the token was confirmed, or the change it records was applied.
        reverted_at: When the "this wasn't me" link of the change was used (email-change tokens only).
    """

    __tablename__ = "sign_up_tokens"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment=("User ID that the sign up token belongs to"),
    )
    token_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
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
    security_generation: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Account security generation an email-change token was issued under (email-change tokens only)",
    )
    change_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True,
        index=True,
        comment="Identifier of the email change the token belongs to (email-change tokens only)",
    )
    revert_until: Mapped[datetime_type | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="End of the email change's revert window (email-change tokens only)",
    )
    confirmed_at: Mapped[datetime_type | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the token was confirmed, or the email change it records was applied",
    )
    reverted_at: Mapped[datetime_type | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the email change's revert link was used (email-change tokens only)",
    )
