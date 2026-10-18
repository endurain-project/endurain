"""CRUD operations for follower relationships."""

from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.followers.constants as followers_constants
import modules.followers.models as followers_models
import modules.followers.schema as followers_schema
import modules.followers.serializers as followers_serializers

# Key under which a request's resolved followee lists are memoized on the
# session. ``Session.info`` is per-session storage and a session is per-request,
# so the cache cannot outlive the request that filled it.
_FOLLOWEE_CACHE_KEY = "followers.accepted_followee_ids"

#: The name of the model's unique (follower, followee) constraint.
_UNIQUE_PAIR_CONSTRAINT = "uq_followers_follower_followee"


def _invalidate_followee_cache(db: Session) -> None:
    """Drop the session's memoized followee lists after a write to the graph.

    Args:
        db: Database session whose cache is cleared.
    """
    db.info.pop(_FOLLOWEE_CACHE_KEY, None)


def _is_duplicate_pair(err: IntegrityError) -> bool:
    """Whether an integrity error is the unique (follower, followee) pair.

    Args:
        err: The integrity error raised by the flush.

    Returns:
        True for the unique-pair violation; False for anything else, which for
        this insert is the foreign key to ``users``.
    """
    constraint = getattr(getattr(err.orig, "diag", None), "constraint_name", None)
    if constraint is not None:
        return constraint == _UNIQUE_PAIR_CONSTRAINT
    return "unique" in str(err.orig).lower()


def get_all_followers_by_user_id(
    user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
    accepted_only: bool = False,
) -> list[followers_schema.FollowRelationshipRead]:
    """Retrieve one page of follower records where the user is being followed.

    Paginated rather than unbounded: a popular account's follower list would
    otherwise be a single unbounded query and response, growing without limit.
    Ordered by ``id`` so paging is stable across requests.

    Args:
        user_id: ID of the user whose followers to retrieve.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.
        accepted_only: Exclude pending follow requests when True.

    Returns:
        The follow relationships on this page (empty list if none).
    """
    stmt = select(followers_models.Follower).where(followers_models.Follower.followee_id == user_id)
    if accepted_only:
        stmt = stmt.where(followers_models.Follower.status == followers_constants.FollowStatus.ACCEPTED.value)
    stmt = stmt.order_by(followers_models.Follower.id).offset((page_number - 1) * num_records).limit(num_records)
    return [followers_serializers.to_read_schema(follower) for follower in db.scalars(stmt).all()]


def get_all_following_by_user_id(
    user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
    accepted_only: bool = False,
) -> list[followers_schema.FollowRelationshipRead]:
    """Retrieve one page of follow records where the user is the follower.

    Paginated for the same reason as :func:`get_all_followers_by_user_id`, and
    ordered by ``id`` so paging is stable.

    Args:
        user_id: ID of the user whose following list to retrieve.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.
        accepted_only: Exclude pending follow requests when True.

    Returns:
        The follow relationships on this page (empty list if none).
    """
    stmt = select(followers_models.Follower).where(followers_models.Follower.follower_id == user_id)
    if accepted_only:
        stmt = stmt.where(followers_models.Follower.status == followers_constants.FollowStatus.ACCEPTED.value)
    stmt = stmt.order_by(followers_models.Follower.id).offset((page_number - 1) * num_records).limit(num_records)
    return [followers_serializers.to_read_schema(follower) for follower in db.scalars(stmt).all()]


def get_pending_requests_for_user_id(
    user_id: int,
    db: Session,
    *,
    page_number: int = 1,
    num_records: int = core_pagination.DEFAULT_NUM_RECORDS,
) -> list[followers_schema.FollowRelationshipRead]:
    """Retrieve one page of pending follow requests addressed to a user.

    Args:
        user_id: The user the requests are addressed to.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.

    Returns:
        The pending requests (empty list if none).
    """
    stmt = (
        select(followers_models.Follower)
        .where(
            followers_models.Follower.followee_id == user_id,
            followers_models.Follower.status == followers_constants.FollowStatus.PENDING.value,
        )
        .order_by(followers_models.Follower.id)
        .offset((page_number - 1) * num_records)
        .limit(num_records)
    )
    return [followers_serializers.to_read_schema(follower) for follower in db.scalars(stmt).all()]


def count_pending_requests_for_user_id(user_id: int, db: Session) -> int:
    """Count the pending follow requests addressed to a user.

    Args:
        user_id: The user the requests are addressed to.
        db: Database session.

    Returns:
        The number of pending requests.
    """
    stmt = select(func.count(followers_models.Follower.id)).where(
        followers_models.Follower.followee_id == user_id,
        followers_models.Follower.status == followers_constants.FollowStatus.PENDING.value,
    )
    return db.scalar(stmt) or 0


def count_followers_by_user_id(user_id: int, db: Session, *, accepted_only: bool = False) -> int:
    """Count followers for a user without loading the full rowset.

    Args:
        user_id: ID of the user whose followers to count.
        db: Database session.
        accepted_only: If True, count only accepted relationships.

    Returns:
        Number of follow relationships.
    """
    stmt = (
        select(func.count())
        .select_from(followers_models.Follower)
        .where(followers_models.Follower.followee_id == user_id)
    )
    if accepted_only:
        stmt = stmt.where(followers_models.Follower.status == followers_constants.FollowStatus.ACCEPTED.value)
    return db.scalar(stmt) or 0


def count_following_by_user_id(user_id: int, db: Session, *, accepted_only: bool = False) -> int:
    """Count users a given user is following without loading the rowset.

    Args:
        user_id: ID of the user whose following list to count.
        db: Database session.
        accepted_only: If True, count only accepted relationships.

    Returns:
        Number of follow relationships.
    """
    stmt = (
        select(func.count())
        .select_from(followers_models.Follower)
        .where(followers_models.Follower.follower_id == user_id)
    )
    if accepted_only:
        stmt = stmt.where(followers_models.Follower.status == followers_constants.FollowStatus.ACCEPTED.value)
    return db.scalar(stmt) or 0


def get_follower_for_user_id_and_target_user_id(
    user_id: int, target_user_id: int, db: Session
) -> followers_schema.FollowRelationshipRead | None:
    """Retrieve a single follow relationship between two users.

    Args:
        user_id: ID of the follower user.
        target_user_id: ID of the user being followed.
        db: Database session.

    Returns:
        The follow relationship if found, otherwise None.
    """
    stmt = select(followers_models.Follower).where(
        followers_models.Follower.follower_id == user_id,
        followers_models.Follower.followee_id == target_user_id,
    )
    follower = db.scalars(stmt).first()
    return followers_serializers.to_read_schema(follower) if follower is not None else None


def list_accepted_followee_ids(user_id: int, db: Session) -> list[int]:
    """List the ids of users the given user follows with an accepted relationship.

    This is the clean read interface the activities feed and visibility filter
    consume instead of reaching into the followers table directly.

    Memoized on the session, which is per-request (``core.database.get_db``).
    A single request asks this repeatedly for an answer that cannot change
    underneath it: a paginated activity list resolves it once for the page and
    again for the matching total, and an activity detail page asks once more per
    child resource through the visibility gate. Any write to the graph clears
    the cache (:func:`_invalidate_followee_cache`), so a request that accepts a
    follow and then reads a feed still sees its own write.

    Args:
        user_id: The follower whose accepted followees to list.
        db: Database session.

    Returns:
        The followee user ids (empty list if none).
    """
    cache: dict[int, list[int]] = db.info.setdefault(_FOLLOWEE_CACHE_KEY, {})
    if user_id in cache:
        return cache[user_id]

    stmt = select(followers_models.Follower.followee_id).where(
        followers_models.Follower.follower_id == user_id,
        followers_models.Follower.status == followers_constants.FollowStatus.ACCEPTED.value,
    )
    followee_ids = list(db.scalars(stmt).all())
    cache[user_id] = followee_ids
    return followee_ids


def create_follower(
    user_id: int,
    target_user_id: int,
    db: Session,
) -> followers_schema.FollowRelationshipRead:
    """Stage a new follow request between two users.

    Flushes without committing: the service owns the transaction, and the
    resulting follower notification (and its websocket push) is produced by the
    ``follower.requested`` subscriber, which the service triggers when it commits.

    Args:
        user_id: ID of the follower user.
        target_user_id: ID of the user being followed.
        db: Database session.

    Returns:
        The newly created Follower relationship as a DTO.

    Raises:
        ConflictError: If the relationship already exists.
    """
    # Pre-check to return a clean 409 instead of a 500 from a unique
    # constraint violation.
    existing = get_follower_for_user_id_and_target_user_id(user_id, target_user_id, db)
    if existing is not None:
        raise core_exceptions.ConflictError("Follow relationship already exists")

    new_follow = followers_models.Follower(
        follower_id=user_id,
        followee_id=target_user_id,
        status=followers_constants.FollowStatus.PENDING.value,
    )

    try:
        db.add(new_follow)
        db.flush()
        db.refresh(new_follow)
        _invalidate_followee_cache(db)
    except IntegrityError as err:
        # Two different constraints can land here. The pre-check above races, so a
        # concurrent follow hits the unique pair and must be a 409, not a 500; a
        # target user that does not exist hits the foreign key and is a 404, not a
        # claim that a relationship already exists. Rolling the session back is the
        # transaction owner's job (``service`` / ``core.database.get_db``), not
        # persistence's.
        if _is_duplicate_pair(err):
            raise core_exceptions.ConflictError("Follow relationship already exists") from err
        raise core_exceptions.NotFoundError("User not found") from err

    return followers_serializers.to_read_schema(new_follow)


def accept_follower(
    user_id: int,
    target_user_id: int,
    db: Session,
) -> followers_schema.FollowRelationshipRead:
    """Stage the acceptance of a pending follow request from another user.

    Flushes without committing: the service owns the transaction, and the
    acceptance notification (and its websocket push) is produced by the
    ``follower.accepted`` subscriber, which the service triggers when it commits.

    Args:
        user_id: ID of the user accepting the request (the followed user).
        target_user_id: ID of the user whose follow request is accepted.
        db: Database session.

    Returns:
        The accepted relationship as a DTO, read back after the flush.

    Raises:
        NotFoundError: If no pending request exists.
    """
    # One conditional UPDATE rather than read-then-write: two concurrent accepts
    # of the same request cannot both succeed, so only one of them publishes the
    # acceptance event.
    stmt = (
        update(followers_models.Follower)
        .where(
            followers_models.Follower.follower_id == target_user_id,
            followers_models.Follower.followee_id == user_id,
            followers_models.Follower.status == followers_constants.FollowStatus.PENDING.value,
        )
        .values(status=followers_constants.FollowStatus.ACCEPTED.value)
        .returning(followers_models.Follower)
        .execution_options(synchronize_session="fetch")
    )

    accept_follow = db.execute(stmt).scalars().first()
    if accept_follow is None:
        raise core_exceptions.NotFoundError("Follower record not found")

    db.flush()
    db.refresh(accept_follow)
    _invalidate_followee_cache(db)

    return followers_serializers.to_read_schema(accept_follow)


def delete_follower(
    user_id: int,
    target_user_id: int,
    db: Session,
    *,
    status: followers_constants.FollowStatus | None = None,
) -> None:
    """Stage the deletion of a follow relationship between two users.

    Flushes without committing, like :func:`create_follower` and
    :func:`accept_follower`; the service owns the transaction boundary.

    Args:
        user_id: ID of the follower user.
        target_user_id: ID of the user being followed.
        db: Database session.
        status: When given, only delete the row if it is in this state. Declining
            a request must not double as removing an accepted follower.

    Raises:
        NotFoundError: If no matching follower record exists.
    """
    stmt = delete(followers_models.Follower).where(
        followers_models.Follower.follower_id == user_id,
        followers_models.Follower.followee_id == target_user_id,
    )
    if status is not None:
        stmt = stmt.where(followers_models.Follower.status == status.value)
    result = cast("CursorResult[Any]", db.execute(stmt))

    if result.rowcount == 0:
        raise core_exceptions.NotFoundError("Follower record not found")

    db.flush()
    _invalidate_followee_cache(db)
