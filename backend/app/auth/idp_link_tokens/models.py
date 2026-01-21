from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from core.database import Base


class IdpLinkToken(Base):
    """
    One-time token for securely linking identity providers to user accounts.

    This provides enhanced security over passing access tokens in query parameters
    by using short-lived (60 seconds), single-use tokens specifically scoped for
    IdP linking operations.

    Attributes:
        id: Primary key, random token (secrets.token_urlsafe(32)).
        user_id: Foreign key to users - the user linking the IdP.
        idp_id: Foreign key to identity_providers - the IdP being linked.
        created_at: Token creation timestamp.
        expires_at: Hard expiry at 60 seconds from creation.
        used: Single-use flag to prevent replay attacks.
        ip_address: Client IP address for optional validation.
        user: Relationship to Users model.
        identity_provider: Relationship to IdentityProvider model.
    """

    __tablename__ = "idp_link_tokens"

    id = Column(
        String(64),
        primary_key=True,
        index=True,
        comment="One-time link token (secrets.token_urlsafe(32))",
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID linking the identity provider",
    )

    idp_id = Column(
        Integer,
        ForeignKey("identity_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Identity provider ID being linked",
    )

    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="Token creation timestamp",
    )

    expires_at = Column(
        DateTime,
        nullable=False,
        index=True,
        comment="Token expiry at 60 seconds (cleanup marker)",
    )

    used = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="Single-use flag (False - unused, True - used)",
    )

    ip_address = Column(
        String(45),
        nullable=True,
        comment="Client IP address (IPv6 max length)",
    )

    # Relationships
    users = relationship("Users", foreign_keys=[user_id])
    identity_provider = relationship("IdentityProvider", foreign_keys=[idp_id])
