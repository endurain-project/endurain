"""SQLAlchemy ORM model for follower relationships."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
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


class FollowerBlock(Base, TimestampMixin):
    """A user's block of another user: the blocked user cannot request to follow the blocker.

    Attributes:
        id: Surrogate primary key.
        blocker_id: The user who blocked.
        blocked_id: The user who is blocked.
    """

    __tablename__ = "follower_blocks"
    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_follower_blocks_blocker_blocked"),
        CheckConstraint("blocker_id <> blocked_id", name="ck_follower_blocks_not_self"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    blocker_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID of the user who blocked",
    )
    blocked_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID of the user who is blocked",
    )


class FollowRequestDecline(Base):
    """When a follow request was last declined, so the requester cannot ask again at once.

    Declining deletes the request itself, so this row is the only record of it.

    Attributes:
        id: Surrogate primary key.
        follower_id: The requester whose request was declined.
        followee_id: The user who declined it.
        declined_at: When the request was declined.
    """

    __tablename__ = "follow_request_declines"
    __table_args__ = (
        UniqueConstraint("follower_id", "followee_id", name="uq_follow_request_declines_follower_followee"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    follower_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID of the requester whose request was declined",
    )
    followee_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="ID of the user who declined the request",
    )
    declined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the request was declined",
    )
