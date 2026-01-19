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
        Boolean,
        nullable=False,
        default=False,
        comment="Token usage status (False - unused, True - used)",
    )

    # Define a relationship to the Users model
    users = relationship("Users", back_populates="password_reset_tokens")
