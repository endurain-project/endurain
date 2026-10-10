"""Auth-owned session database models (table: ``users_sessions``)."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.auth.oauth_state.models import OAuthState
    from modules.auth.sessions.rotated_refresh_tokens.models import (
        RotatedRefreshToken,
    )


class UsersSessions(Base):
    """
    User authentication session for tracking active logins.

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
        oauth_state: Relationship to OAuthState model.
        rotated_refresh_tokens: Relationship to
            RotatedRefreshToken model.
    """

    __tablename__ = "users_sessions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
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
        comment="Last activity timestamp for idle timeout",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
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
    token_family_id: Mapped[str] = mapped_column(
        String(36),
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

    # Relationship to OAuthState model
    oauth_state: Mapped["OAuthState | None"] = relationship(back_populates="users_sessions")

    # Relationship to RotatedRefreshToken model
    rotated_refresh_tokens: Mapped[list["RotatedRefreshToken"]] = relationship(
        back_populates="users_session",
        cascade="all, delete-orphan",
    )
