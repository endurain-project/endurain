"""SQLAlchemy ORM model for follower relationships."""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base, TimestampMixin
from modules.followers.constants import FollowStatus

if TYPE_CHECKING:
    from modules.users.users.models import Users


class Follower(Base, TimestampMixin):
    """Follow relationship between two users."""

    __tablename__ = "followers"
    __table_args__ = (UniqueConstraint("follower_id", "followee_id", name="uq_followers_follower_followee"),)

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        index=True,
    )
    follower_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID of the follower user (the requester)",
    )
    followee_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID of the followee user (the target being followed)",
    )
    status: Mapped[str] = mapped_column(
        String(length=20),
        nullable=False,
        default=FollowStatus.PENDING.value,
        server_default=FollowStatus.PENDING.value,
        comment="Follow request status: pending or accepted",
    )

    # Relationships to the Users model. Defined for completeness and ORM-level
    # cascade on user deletion; the module queries by explicit columns rather
    # than navigating these.
    follower: Mapped["Users"] = relationship(foreign_keys=[follower_id], back_populates="following")
    followee: Mapped["Users"] = relationship(foreign_keys=[followee_id], back_populates="followers")
