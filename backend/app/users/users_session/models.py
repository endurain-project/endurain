from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Boolean,
)
from sqlalchemy.orm import relationship
from core.database import Base


class UsersSessions(Base):
    """
    Represents a user session in the system.

    Attributes:
        id (str): Unique identifier for the session (UUID).
        user_id (int): ID of the user to whom the session belongs.
        refresh_token (str): Hashed refresh token for the session.
        csrf_token_hash (str): Hashed CSRF token for refresh validation.
        ip_address (str): IP address of the client initiating the session.
        device_type (str): Type of device used for the session.
        operating_system (str): Operating system of the device.
        operating_system_version (str): Version of the operating system.
        browser (str): Browser used for the session.
        browser_version (str): Version of the browser.
        created_at (datetime): Timestamp when the session was created.
        last_activity_at (datetime): Timestamp of last user activity.
        expires_at (datetime): Timestamp when the session expires.
        user (User): Relationship to the Users model.
        rotated_refresh_tokens (list): Rotated tokens for this session.
    """

    __tablename__ = "users_sessions"

    id = Column(String(length=36), nullable=False, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the session belongs",
    )
    refresh_token = Column(
        String(length=255), nullable=False, comment="Session hashed refresh token"
    )
    ip_address = Column(String(45), nullable=False, comment="Client IP address")
    device_type = Column(String(length=45), nullable=False, comment="Device type")
    operating_system = Column(
        String(length=45), nullable=False, comment="Operating system"
    )
    operating_system_version = Column(
        String(length=45), nullable=False, comment="Operating system version"
    )
    browser = Column(String(length=45), nullable=False, comment="Browser")
    browser_version = Column(
        String(length=45), nullable=False, comment="Browser version"
    )
    created_at = Column(
        DateTime, nullable=False, comment="Session creation date (datetime)"
    )
    last_activity_at = Column(
        DateTime, nullable=False, comment="Last activity timestamp for idle timeout"
    )
    expires_at = Column(
        DateTime, nullable=False, comment="Session expiration date (datetime)"
    )
    oauth_state_id = Column(
        String(64),
        ForeignKey("oauth_states.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Link to OAuth state for PKCE validation",
    )
    tokens_exchanged = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="Prevents duplicate token exchange for mobile",
    )
    token_family_id = Column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
        comment="UUID identifying token family for reuse detection",
    )
    rotation_count = Column(
        Integer,
        default=0,
        nullable=False,
        comment="Number of times refresh token has been rotated",
    )
    last_rotation_at = Column(
        DateTime, nullable=True, comment="Timestamp of last token rotation"
    )
    csrf_token_hash = Column(
        String(length=255),
        nullable=True,
        comment="Hashed CSRF token for refresh validation",
    )

    # Define a relationship to the Users model
    users = relationship("Users", back_populates="users_sessions")

    # Define a relationship to the OAuthState model
    oauth_state = relationship("OAuthState", back_populates="users_sessions")

    # Define a relationship to RotatedRefreshToken model
    rotated_refresh_tokens = relationship(
        "RotatedRefreshToken",
        back_populates="user_session",
        cascade="all, delete-orphan",
    )
