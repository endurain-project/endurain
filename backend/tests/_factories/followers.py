"""Follow relationships as the application stores them, for tests on the real database."""

import uuid
from datetime import datetime

from sqlalchemy import update
from sqlalchemy.orm import Session

import modules.followers.crud as followers_crud
import modules.followers.models as followers_models
import modules.followers.schema as followers_schema


def make_follow(
    db: Session, follower_id: uuid.UUID, followee_id: uuid.UUID, *, accepted: bool
) -> followers_schema.FollowRelationshipRead:
    """Stage a follow relationship through the module's create and accept functions (flushed, not committed).

    Args:
        db: Database session.
        follower_id: The user who follows.
        followee_id: The user who is followed.
        accepted: Whether the followee accepted the request; otherwise it stays pending.

    Returns:
        The staged relationship.
    """
    follow = followers_crud.create_follower(follower_id, followee_id, db)
    if accepted:
        return followers_crud.accept_follower(followee_id, follower_id, db)
    return follow


def make_follow_at(
    db: Session, follower_id: uuid.UUID, followee_id: uuid.UUID, created_at: datetime, *, accepted: bool
) -> followers_schema.FollowRelationshipRead:
    """Stage a follow relationship created at a chosen time (flushed, not committed).

    The database stamps ``created_at`` with the transaction's start, so rows staged in one transaction share it; a
    test of the listing order arranges the times itself.

    Args:
        db: Database session.
        follower_id: The user who follows.
        followee_id: The user who is followed.
        created_at: When the relationship was created.
        accepted: Whether the followee accepted the request; otherwise it stays pending.

    Returns:
        The staged relationship.
    """
    follow = make_follow(db, follower_id, followee_id, accepted=accepted)
    db.execute(
        update(followers_models.Follower)
        .where(
            followers_models.Follower.follower_id == follower_id,
            followers_models.Follower.followee_id == followee_id,
        )
        .values(created_at=created_at)
    )
    db.flush()
    return follow


def make_block(
    db: Session, blocker_id: uuid.UUID, blocked_id: uuid.UUID, *, created_at: datetime | None = None
) -> None:
    """Stage a block through the module's create function (flushed, not committed).

    Only the block row is written: the follows between the two are left alone, and nothing is audited or published.

    Args:
        db: Database session.
        blocker_id: The user who blocks.
        blocked_id: The user who is blocked.
        created_at: When the block was made; the transaction's start when omitted.
    """
    followers_crud.create_block(blocker_id, blocked_id, db)
    if created_at is not None:
        db.execute(
            update(followers_models.FollowerBlock)
            .where(
                followers_models.FollowerBlock.blocker_id == blocker_id,
                followers_models.FollowerBlock.blocked_id == blocked_id,
            )
            .values(created_at=created_at)
        )
        db.flush()


def make_decline(db: Session, follower_id: uuid.UUID, followee_id: uuid.UUID, declined_at: datetime) -> None:
    """Stage the decline of a follow request through the module's own function (flushed, not committed).

    Args:
        db: Database session.
        follower_id: The requester whose request was declined.
        followee_id: The user who declined it.
        declined_at: When the request was declined.
    """
    followers_crud.record_decline(follower_id, followee_id, declined_at, db)
