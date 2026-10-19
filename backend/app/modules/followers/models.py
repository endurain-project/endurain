"""SQLAlchemy ORM model for follower relationships."""

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

import modules.followers.constants as followers_constants
from core.database import Base, TimestampMixin


class Follower(Base, TimestampMixin):
    """Follow relationship between two users.

    Attributes:
        id: Surrogate primary key.
        follower_id: The user who follows (the requester).
        followee_id: The user being followed.
        status: ``pending`` until the followee accepts, then ``accepted``.
    """

    __tablename__ = "followers"
    __table_args__ = (
        UniqueConstraint("follower_id", "followee_id", name="uq_followers_follower_followee"),
        CheckConstraint("follower_id <> followee_id", name="ck_followers_not_self"),
        CheckConstraint("status IN ('pending', 'accepted')", name="ck_followers_status"),
    )

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
        default=followers_constants.FollowStatus.PENDING.value,
        server_default=followers_constants.FollowStatus.PENDING.value,
        comment="Follow request status: pending or accepted",
    )
