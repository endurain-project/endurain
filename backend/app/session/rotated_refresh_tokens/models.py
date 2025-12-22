from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from core.database import Base


class RotatedRefreshToken(Base):
    """
    Represents a rotated refresh token in the system.

    Attributes:
        id: Unique identifier for the rotated token.
        token_family_id: UUID of the token family.
        hashed_token: Hashed old refresh token.
        rotation_count: Which rotation this token belonged to.
        rotated_at: When this token was rotated.
        expires_at: Cleanup marker (rotated_at + 60 seconds).
        user_session: Relationship to UsersSessions model.
    """

    __tablename__ = "rotated_refresh_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token_family_id = Column(
        String(36),
        ForeignKey("users_sessions.token_family_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="UUID of the token family",
    )
    hashed_token = Column(
        String(255), nullable=False, unique=True, comment="Hashed old refresh token"
    )
    rotation_count = Column(
        Integer, nullable=False, comment="Which rotation this token belonged to"
    )
    rotated_at = Column(DateTime, nullable=False, comment="When this token was rotated")
    expires_at = Column(
        DateTime, nullable=False, comment="Cleanup marker (rotated_at + 60 seconds)"
    )

    # Define a relationship to UsersSessions model
    user_session = relationship(
        "UsersSessions",
        back_populates="rotated_refresh_tokens",
    )
