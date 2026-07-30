"""SQLAlchemy ORM model for the ``users_mfa`` table.

This module defines the 1:1 companion table that owns MFA
state for a user. Rows are written by
``auth.mfa.crud.update_user_mfa`` and created by
``auth.mfa.crud.create_users_mfa_row``; the legacy
``users.mfa_enabled`` / ``users.mfa_secret`` columns no
longer exist.
"""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class UsersMFA(Base):
    """
    1:1 MFA state table keyed by user_id.

    Stores ``mfa_enabled`` and ``mfa_secret`` as the sole
    source of truth for a user's MFA state.

    Attributes:
        id: Surrogate primary key.
        user_id: FK to ``users.id`` (unique — one row per
            user).
        mfa_enabled: Whether TOTP MFA is active for the
            user.
        mfa_secret: Fernet-encrypted TOTP secret, or
            ``None`` when MFA is disabled.
    """

    __tablename__ = "users_mfa"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            name="uq_users_mfa_user_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="FK to users — one row per user",
    )
    mfa_enabled: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Whether TOTP MFA is active for this user",
    )
    mfa_secret: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="Fernet-encrypted TOTP secret",
    )
