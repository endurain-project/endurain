"""Follow relationships as the application stores them, for tests on the real database."""

import uuid

from sqlalchemy.orm import Session

import modules.followers.crud as followers_crud
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
