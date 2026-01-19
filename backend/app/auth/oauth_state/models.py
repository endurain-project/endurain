from sqlalchemy import Column, String, Integer, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from core.database import Base


class OAuthState(Base):
    """
    Server-side storage for OAuth/SSO flow state.

    This replaces cookie-based state with database persistence
    for enhanced security and mobile support. Stores PKCE
    challenges, OIDC nonce, and flow metadata.

    Attributes:
        id: Primary key, state parameter itself (random UUID).
        idp_id: Foreign key to identity_provider.
        user_id: Foreign key to users (for link mode, nullable).
        code_challenge: PKCE challenge (base64url-encoded).
        code_challenge_method: PKCE method (always S256).
        nonce: OIDC nonce for ID token validation.
        redirect_path: Frontend path after login.
        client_type: web or mobile.
        ip_address: Client IP for optional validation.
        created_at: Timestamp for expiry calculation.
        expires_at: Hard expiry at 10 minutes.
        used: Prevents replay attacks.
        identity_provider: Relationship to IdentityProvider model.
        user: Relationship to Users model (nullable).
        users_sessions: Relationship to UsersSessions model.
    """

    __tablename__ = "oauth_states"

    id = Column(
        String(64),
        primary_key=True,
        index=True,
        comment="State parameter itself (secrets.token_urlsafe(32))",
    )

    idp_id = Column(
        Integer,
        ForeignKey("identity_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Identity provider ID",
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="User ID (for link mode)",
    )

    code_challenge = Column(
        String(128), nullable=True, comment="Base64url-encoded SHA256(code_verifier)"
    )

    code_challenge_method = Column(
        String(10), nullable=True, comment="PKCE method (only S256 supported)"
    )

    nonce = Column(
        String(64), nullable=False, comment="OIDC nonce for ID token validation"
    )

    redirect_path = Column(
        String(500), nullable=True, comment="Frontend path after login"
    )

    client_type = Column(
        String(10), nullable=False, comment="Client type: web or mobile"
    )

    ip_address = Column(
        String(45), nullable=True, comment="Client IP address (IPv6 max length)"
    )

    created_at = Column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="OAuth state creation timestamp",
    )

    expires_at = Column(
        DateTime,
        nullable=False,
        index=True,
        comment="Hard expiry at 10 minutes (cleanup marker)",
    )

    used = Column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="True when state is consumed (prevents replay)",
    )

    # Relationships
    identity_provider = relationship("IdentityProvider", back_populates="oauth_states")
    users = relationship("Users", back_populates="oauth_states")
    users_sessions = relationship("UsersSessions", back_populates="oauth_state")
