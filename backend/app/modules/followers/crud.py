"""CRUD operations for follower relationships."""

from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import core.logger as core_logger
import modules.followers.models as followers_models
import modules.followers.schema as followers_schema

logger = core_logger.get_logger(__name__)


def _transform_follower(follower: followers_models.Follower) -> followers_schema.FollowRelationship:
    """Convert a Follower ORM row into its serialized DTO."""
    return followers_schema.FollowRelationship.model_validate(follower)


@core_decorators.handle_db_errors
def get_all_followers_by_user_id(user_id: int, db: Session) -> list[followers_schema.FollowRelationship]:
    """
    Retrieve all follower records where the user is being followed.

    Args:
        user_id: ID of the user whose followers to retrieve.
        db: Database session.

    Returns:
        List of Follower records (empty list if none).

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(followers_models.Follower).where(followers_models.Follower.followee_id == user_id)
    return [_transform_follower(follower) for follower in db.scalars(stmt).all()]


@core_decorators.handle_db_errors
def get_accepted_followers_by_user_id(user_id: int, db: Session) -> list[followers_schema.FollowRelationship]:
    """
    Retrieve accepted follower records where the user is being followed.

    Args:
        user_id: ID of the user whose accepted followers to retrieve.
        db: Database session.

    Returns:
        List of accepted Follower records (empty list if none).

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(followers_models.Follower).where(
        followers_models.Follower.followee_id == user_id,
        followers_models.Follower.status == "accepted",
    )
    return [_transform_follower(follower) for follower in db.scalars(stmt).all()]


@core_decorators.handle_db_errors
def get_all_following_by_user_id(user_id: int, db: Session) -> list[followers_schema.FollowRelationship]:
    """
    Retrieve all follow records where the user is the follower.

    Args:
        user_id: ID of the user whose following list to retrieve.
        db: Database session.

    Returns:
        List of Follower records (empty list if none).

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(followers_models.Follower).where(followers_models.Follower.follower_id == user_id)
    return [_transform_follower(follower) for follower in db.scalars(stmt).all()]


@core_decorators.handle_db_errors
def get_accepted_following_by_user_id(user_id: int, db: Session) -> list[followers_schema.FollowRelationship]:
    """
    Retrieve accepted follow records where the user is the follower.

    Args:
        user_id: ID of the user whose accepted following list to retrieve.
        db: Database session.

    Returns:
        List of accepted Follower records (empty list if none).

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(followers_models.Follower).where(
        followers_models.Follower.follower_id == user_id,
        followers_models.Follower.status == "accepted",
    )
    return [_transform_follower(follower) for follower in db.scalars(stmt).all()]


@core_decorators.handle_db_errors
def count_followers_by_user_id(user_id: int, db: Session, *, accepted_only: bool = False) -> int:
    """
    Count followers for a user without loading the full rowset.

    Args:
        user_id: ID of the user whose followers to count.
        db: Database session.
        accepted_only: If True, count only accepted relationships.

    Returns:
        Number of follower records.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = (
        select(func.count())
        .select_from(followers_models.Follower)
        .where(followers_models.Follower.followee_id == user_id)
    )
    if accepted_only:
        stmt = stmt.where(followers_models.Follower.status == "accepted")
    return db.scalar(stmt) or 0


@core_decorators.handle_db_errors
def count_following_by_user_id(user_id: int, db: Session, *, accepted_only: bool = False) -> int:
    """
    Count users a given user is following without loading the rowset.

    Args:
        user_id: ID of the user whose following list to count.
        db: Database session.
        accepted_only: If True, count only accepted relationships.

    Returns:
        Number of follow records.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = (
        select(func.count())
        .select_from(followers_models.Follower)
        .where(followers_models.Follower.follower_id == user_id)
    )
    if accepted_only:
        stmt = stmt.where(followers_models.Follower.status == "accepted")
    return db.scalar(stmt) or 0


@core_decorators.handle_db_errors
def get_follower_for_user_id_and_target_user_id(
    user_id: int, target_user_id: int, db: Session
) -> followers_schema.FollowRelationship | None:
    """
    Retrieve a single follow relationship between two users.

    Args:
        user_id: ID of the follower user.
        target_user_id: ID of the user being followed.
        db: Database session.

    Returns:
        Follower record if found, otherwise None.

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(followers_models.Follower).where(
        followers_models.Follower.follower_id == user_id,
        followers_models.Follower.followee_id == target_user_id,
    )
    follower = db.scalars(stmt).first()
    return _transform_follower(follower) if follower is not None else None


@core_decorators.handle_db_errors
def list_accepted_followee_ids(user_id: int, db: Session) -> list[int]:
    """List the ids of users the given user follows with an accepted relationship.

    This is the clean read interface the activities feed and visibility filter
    consume instead of reaching into the followers table directly.

    Args:
        user_id: The follower whose accepted followees to list.
        db: Database session.

    Returns:
        The followee user ids (empty list if none).

    Raises:
        HTTPException: If a database error occurs.
    """
    stmt = select(followers_models.Follower.followee_id).where(
        followers_models.Follower.follower_id == user_id,
        followers_models.Follower.status == "accepted",
    )
    return list(db.scalars(stmt).all())


@core_decorators.handle_db_errors
def create_follower(
    user_id: int,
    target_user_id: int,
    db: Session,
) -> followers_schema.FollowRelationship:
    """
    Create a new follow request between two users.

    Side-effect-free: the resulting follower notification (and its websocket push)
    is produced by the ``follower.requested`` subscriber, which the follow service
    triggers after this row is committed.

    Args:
        user_id: ID of the follower user.
        target_user_id: ID of the user being followed.
        db: Database session.

    Returns:
        The newly created Follower relationship as a DTO.

    Raises:
        HTTPException: 400 if attempting to follow self, 409 if relationship
            already exists, 500 on database errors.
    """
    # Prevent self-follow which would otherwise pollute counts and
    # notifications.
    if user_id == target_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot follow yourself",
        )

    # Pre-check to return a clean 409 instead of a 500 from a unique
    # constraint violation.
    existing = get_follower_for_user_id_and_target_user_id(user_id, target_user_id, db)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Follow relationship already exists",
        )

    new_follow = followers_models.Follower(
        follower_id=user_id,
        followee_id=target_user_id,
        status="pending",
    )

    try:
        db.add(new_follow)
        db.commit()
        db.refresh(new_follow)
    except IntegrityError as err:
        # Kept rather than delegated: the decorator deliberately lets IntegrityError
        # through precisely so a caller can map it to its own semantics. The
        # pre-check above races, so a concurrent follow lands here and must be a
        # 409, not a 500. Everything else is the decorator's job.
        db.rollback()
        logger.warning(f"Integrity error in create_follower: {type(err).__name__}", exc_info=err)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Follow relationship already exists",
        ) from err

    return _transform_follower(new_follow)


@core_decorators.handle_db_errors
def accept_follower(
    user_id: int,
    target_user_id: int,
    db: Session,
) -> None:
    """
    Accept a pending follow request from another user.

    Side-effect-free: the acceptance notification (and its websocket push) is
    produced by the ``follower.accepted`` subscriber, which the follow service
    triggers after this row is committed.

    Args:
        user_id: ID of the user accepting the request (the followed user).
        target_user_id: ID of the user whose follow request is accepted.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: 404 if no pending request exists, 500 on database
            errors.
    """
    stmt = select(followers_models.Follower).where(
        followers_models.Follower.follower_id == target_user_id,
        followers_models.Follower.followee_id == user_id,
        followers_models.Follower.status == "pending",
    )

    accept_follow = db.scalars(stmt).first()
    if accept_follow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Follower record not found",
        )

    accept_follow.status = "accepted"
    db.commit()
    db.refresh(accept_follow)


@core_decorators.handle_db_errors
def delete_follower(user_id: int, target_user_id: int, db: Session) -> None:
    """
    Delete a follow relationship between two users.

    Args:
        user_id: ID of the follower user.
        target_user_id: ID of the user being followed.
        db: Database session.

    Returns:
        None.

    Raises:
        HTTPException: 404 if no matching follower record exists, 500 on
            database errors.
    """
    stmt = delete(followers_models.Follower).where(
        followers_models.Follower.follower_id == user_id,
        followers_models.Follower.followee_id == target_user_id,
    )
    result = cast("CursorResult[Any]", db.execute(stmt))

    if result.rowcount == 0:
        # Roll back so the no-op transaction does not stay open.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Follower record not found",
        )

    db.commit()
