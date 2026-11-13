"""Auth-owned session database models (table: ``users_sessions``)."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

import modules.auth.constants as auth_constants
from core.database import Base

#: The values ``client_type`` may hold: one per ``ClientType``.
_CLIENT_TYPE_VALUES = ", ".join(f"'{client_type.value}'" for client_type in auth_constants.ClientType)


class UsersSessions(Base):
    """User authentication session for tracking active logins.

    Attributes:
        id: Unique session identifier (UUID).
        user_id: Foreign key to users table.
        refresh_token: Hashed refresh token for the session.
        ip_address: Client IP address.
        device_type: Type of device (Mobile, Tablet, PC).
        operating_system: Operating system name.
        operating_system_version: Operating system version.
        browser: Browser name.
        browser_version: Browser version.
        created_at: Session creation timestamp.
        last_activity_at: Last activity timestamp for idle
            timeout.
        expires_at: Session expiration timestamp.
        oauth_state_id: Link to OAuth state for PKCE validation.
        tokens_exchanged: Prevents duplicate token exchange for
            mobile.
        token_family_id: UUID identifying token family for reuse
            detection.
        rotation_count: Number of times refresh token has been
            rotated.
        last_rotation_at: Timestamp of last token rotation.
        csrf_token_hash: Hashed CSRF token for refresh
            validation.
        client_type: The client the session was created for (``ClientType``); its tokens name it as
            ``client_id`` and a refresh must declare it.
        auth_time: When the owner signed in; refresh and step-up leave it unchanged.
        app_redirect_uri: The native-app redirect address an SSO sign-in handed the session to; null for a web
            session and for a sign-in that carried no redirect.
        device_hash: SHA-256 hex digest of the known-device id the session signed in from (as ``known_devices``
            stores it); null for a session created before the column existed, which forgetting a device does not end.
        amr: How the owner proved themselves (RFC 8176 values); a session awaiting its SSO token exchange has
            only ``fed``, and the exchange adds the second factor.
    """

    __tablename__ = "users_sessions"
    __table_args__ = (CheckConstraint(f"client_type IN ({_CLIENT_TYPE_VALUES})", name="ck_users_sessions_client_type"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the session belongs",
    )
    refresh_token: Mapped[str] = mapped_column(
        String(255),
        nullable=True,
        comment="Session hashed refresh token",
    )
    ip_address: Mapped[str] = mapped_column(
        String(45),
        nullable=False,
        comment="Client IP address",
    )
    device_type: Mapped[str] = mapped_column(
        String(45),
        nullable=False,
        comment="Device type",
    )
    operating_system: Mapped[str] = mapped_column(
        String(45),
        nullable=False,
        comment="Operating system",
    )
    operating_system_version: Mapped[str] = mapped_column(
        String(45),
        nullable=False,
        comment="Operating system version",
    )
    browser: Mapped[str] = mapped_column(
        String(45),
        nullable=False,
        comment="Browser",
    )
    browser_version: Mapped[str] = mapped_column(
        String(45),
        nullable=False,
        comment="Browser version",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Session creation date (datetime)",
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Last activity timestamp for idle timeout",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Session expiration date (datetime)",
    )
    oauth_state_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("oauth_states.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Link to OAuth state for PKCE validation",
    )
    tokens_exchanged: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
        comment="Prevents duplicate token exchange for mobile",
    )
    token_family_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False,
        unique=True,
        index=True,
        comment="UUID identifying token family for reuse detection",
    )
    rotation_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
        comment="Number of times refresh token has been rotated",
    )
    last_rotation_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last token rotation",
    )
    csrf_token_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Hashed CSRF token for refresh validation",
    )
    client_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Client type the session was created for: web or mobile",
    )
    auth_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the user signed in; refresh and step-up do not change it",
    )
    amr: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        comment="Authentication methods of the sign-in (RFC 8176 values): pwd, fed, otp, mfa",
    )
    app_redirect_uri: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="Native-app redirect address an SSO sign-in handed the session to",
    )
    device_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 hex digest of the device id the session signed in from",
    )
