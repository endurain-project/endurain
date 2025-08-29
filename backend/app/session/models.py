from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from core.database import Base


class UsersSessions(Base):
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
        String(length=500), nullable=False, comment="Session refresh token"
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
    expires_at = Column(
        DateTime, nullable=False, comment="Session expiration date (datetime)"
    )

    # Define a relationship to the User model
    user = relationship("User", back_populates="users_sessions")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(String(length=64), nullable=False, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User ID that the password reset token belongs to",
    )
    token_hash = Column(
        String(length=128), nullable=False, comment="Hashed password reset token"
    )
    created_at = Column(
        DateTime, nullable=False, comment="Token creation date (datetime)"
    )
    expires_at = Column(
        DateTime, nullable=False, comment="Token expiration date (datetime)"
    )
    used = Column(
        Integer, 
        nullable=False, 
        default=0, 
        comment="Token usage status (0 - unused, 1 - used)"
    )

    # Define a relationship to the User model
    user = relationship("User", back_populates="password_reset_tokens")