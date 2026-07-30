"""SQLAlchemy ORM model for the ``users_local_credentials`` table.

This module defines the auth-owned 1:1 companion table that stores a
user's local password hash. It is the credential-ownership counterpart to
the ``users_mfa`` table: auth owns the secret, ``users`` owns the profile.
Rows are written and read through ``auth.credentials.crud``.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base


class LocalCredential(Base):
    """
    Auth-owned local password credential for a user (1:1 with ``users``).

    A row exists only for accounts that have a local password. SSO-only
    accounts have no row, which makes "has a local password" a simple row
    existence check rather than an empty-string sentinel.

    Attributes:
        user_id: FK to ``users.id`` and primary key (one row per user).
        password_hash: Argon2/bcrypt password hash.
        created_at: Row creation timestamp.
        updated_at: Last update timestamp.
    """

    __tablename__ = "users_local_credentials"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    password_hash: Mapped[str] = mapped_column(
        String(250),
        nullable=False,
        comment="Local account password hash",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
