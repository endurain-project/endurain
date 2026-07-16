"""SQLAlchemy ORM model for follower relationships."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from modules.users.users.models import Users


class Follower(Base):
    """Follow relationship between two users."""

    __tablename__ = "followers"

    follower_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
        comment="ID of the follower user",
    )
    following_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
        comment="ID of the following user",
    )
    is_accepted: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether the follow request is accepted or not",
    )

    # Define a relationship to the Users model
    follower: Mapped["Users"] = relationship(foreign_keys=[follower_id], back_populates="followers")
    # Define a relationship to the Users model
    following: Mapped["Users"] = relationship(foreign_keys=[following_id], back_populates="following")
