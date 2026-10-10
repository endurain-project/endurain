"""SQLAlchemy ORM models for IdP link tokens."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base

if TYPE_CHECKING:
    from modules.auth.identity_providers.models import IdentityProvider


class IdpLinkToken(Base):
    """
    One-time token for securely linking identity providers to user accounts.

    This provides enhanced security over passing access tokens in query parameters
    by using short-lived (60 seconds), single-use tokens specifically scoped for
    IdP linking operations.

    Attributes:
        id: Primary key, random UUID.
        token_hash: SHA-256 hash of the plaintext link token.
        user_id: Foreign key to users - the user linking the IdP.
        idp_id: Foreign key to identity_providers - the IdP being linked.
        created_at: Token creation timestamp.
        expires_at: Hard expiry at 60 seconds from creation.
        used: Single-use flag to prevent replay attacks.
        ip_address: Client IP address for optional validation.
        identity_provider: Relationship to IdentityProvider model.
    """

    __tablename__ = "idp_link_tokens"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        index=True,
        comment="Opaque row identifier, not the link token",
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="SHA-256 hash of the one-time link token",
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID linking the identity provider",
    )

    idp_id: Mapped[int] = mapped_column(
        ForeignKey("identity_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Identity provider ID being linked",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Token creation timestamp",
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Token expiry at 60 seconds (cleanup marker)",
    )

    used: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Single-use flag (False - unused, True - used)",
    )

    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Client IP address (IPv6 max length)",
    )

    # Relationships
    identity_provider: Mapped["IdentityProvider"] = relationship(foreign_keys=[idp_id])
