"""SQLAlchemy ORM model for follower relationships."""

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base, TimestampMixin
from modules.followers.constants import FollowStatus


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
