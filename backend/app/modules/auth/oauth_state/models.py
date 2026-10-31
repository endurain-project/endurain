"""SQLAlchemy ORM model for OAuth/SSO flow state persistence."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base


class OAuthState(Base):
    """Server-side storage for OAuth/SSO flow state.

    This replaces cookie-based state with database persistence
    for enhanced security and mobile support. Stores PKCE
    challenges, OIDC nonce, and flow metadata.

    Attributes:
        id: Primary key, state parameter itself (random URL-safe token).
        idp_id: Foreign key to identity_provider.
        user_id: Foreign key to users (the signed-in user of a link or step-up flow, nullable).
        code_challenge: PKCE challenge (base64url-encoded).
        code_challenge_method: PKCE method (always S256).
        nonce: OIDC nonce for ID token validation.
        redirect_path: Frontend path after login.
        client_type: web or mobile.
        ip_address: Client IP for optional validation.
        created_at: Timestamp for expiry calculation.
        expires_at: Hard expiry at 10 minutes.
        used: Prevents replay attacks.
        browser_binding_hash: SHA-256 of the secret the browser that started a link or step-up holds in a cookie.
        idp_code_verifier: PKCE verifier this server sends the identity provider at the token exchange.
        purpose: The flow the state belongs to (``OAuthStatePurpose``).
        session_id: The session that started a step-up flow.
        action: The sensitive operation a step-up flow authorises.
    """

    __tablename__ = "oauth_states"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        index=True,
        comment="State parameter itself (secrets.token_urlsafe(32))",
    )

    idp_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("identity_providers.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Identity provider ID (may be null if mobile logic)",
    )

    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="User ID (for link mode)",
    )

    code_challenge: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="Base64url-encoded SHA256(code_verifier)",
    )

    code_challenge_method: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        comment="PKCE method (only S256 supported)",
    )

    nonce: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="OIDC nonce for ID token validation",
    )

    redirect_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Frontend path after login",
    )

    client_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Client type: web or mobile",
    )

    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        comment="Client IP address (IPv6 max length)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="OAuth state creation timestamp",
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Hard expiry at 10 minutes (cleanup marker)",
    )

    used: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
        comment="True when state is consumed (prevents replay)",
    )

    browser_binding_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 of the browser-binding cookie (link and step-up flows)",
    )

    purpose: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="Flow the state belongs to: login, link or step_up",
    )

    session_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        comment="Session that started a step-up flow (step-up only)",
    )

    action: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment="Sensitive operation a step-up flow authorises (step-up only)",
    )

    idp_code_verifier: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="PKCE verifier sent to the identity provider at the token exchange",
    )
