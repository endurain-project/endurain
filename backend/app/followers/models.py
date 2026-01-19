from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    Boolean,
)
from sqlalchemy.orm import relationship
from core.database import Base


# Data model for followers table using SQLAlchemy's ORM
class Follower(Base):
    __tablename__ = "followers"

    follower_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
        comment="ID of the follower user",
    )
    following_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
        comment="ID of the following user",
    )
    is_accepted = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether the follow request is accepted or not",
    )

    # Define a relationship to the Users model
    follower = relationship(
        "Users", foreign_keys=[follower_id], back_populates="followers"
    )
    # Define a relationship to the Users model
    following = relationship(
        "Users", foreign_keys=[following_id], back_populates="following"
    )
