"""CRUD operations for follower relationships."""

from datetime import datetime

from sqlalchemy import Select, and_, delete, exists, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute, Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.pagination as core_pagination
import core.timezone as core_timezone
import modules.followers.constants as followers_constants
import modules.followers.models as followers_models
import modules.followers.schema as followers_schema
import modules.followers.serializers as followers_serializers

# Key under which a request's resolved followee lists are memoized on the
# session. ``Session.info`` is per-session storage and a session is per-request,
# so the cache cannot outlive the request that filled it.
_FOLLOWEE_CACHE_KEY = "followers.accepted_followee_ids"

#: Advisory-lock namespace of a user's pending follow requests, kept apart from every other advisory lock.
_PENDING_LOCK_NAMESPACE = 7301

#: Advisory-lock namespace of a user's accepted followees, kept apart from every other advisory lock.
_ACCEPTED_LOCK_NAMESPACE = 7302

#: The name of the model's unique (follower, followee) constraint.
_UNIQUE_PAIR_CONSTRAINT = "uq_followers_follower_followee"

#: The name of the block model's unique (blocker, blocked) constraint.
_UNIQUE_BLOCK_CONSTRAINT = "uq_follower_blocks_blocker_blocked"


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
    constraint = core_database.violated_constraint(err)
    if constraint is not None:
        return constraint == _UNIQUE_PAIR_CONSTRAINT
    return "unique" in str(err.orig).lower()


def _filtered(
    column: InstrumentedAttribute[int],
    user_id: int,
    accepted_only: bool,
    pending_only: bool,
) -> Select[tuple[followers_models.Follower]]:
    """Select the follow rows where ``column`` is the user, optionally of one status.

    Args:
        column: ``followee_id`` to list a user's followers, ``follower_id`` to list who they follow.
        user_id: The user the rows belong to.
        accepted_only: Keep only accepted relationships.
        pending_only: Keep only pending requests.

    Returns:
        The unordered, unpaged select.
    """
    stmt = select(followers_models.Follower).where(column == user_id)
    if accepted_only:
        stmt = stmt.where(followers_models.Follower.status == followers_constants.FollowStatus.ACCEPTED.value)
    if pending_only:
        stmt = stmt.where(followers_models.Follower.status == followers_constants.FollowStatus.PENDING.value)
    return stmt


def _page(
    column: InstrumentedAttribute[int],
    user_id: int,
    db: Session,
    *,
    page_number: int,
    num_records: int,
    accepted_only: bool = False,
    pending_only: bool = False,
) -> list[followers_schema.FollowRelationshipRead]:
    """Load one page of follow rows, ordered by creation time, then ``id``, so paging is stable.

    Args:
        column: See :func:`_filtered`.
        user_id: The user the rows belong to.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.
        accepted_only: Keep only accepted relationships.
        pending_only: Keep only pending requests.

    Returns:
        The follow relationships on this page (empty list if none).
    """
    stmt = (
        _filtered(column, user_id, accepted_only, pending_only)
        .order_by(followers_models.Follower.created_at, followers_models.Follower.id)
        .offset((page_number - 1) * num_records)
        .limit(num_records)
    )
    return [followers_serializers.to_read_schema(follower) for follower in db.scalars(stmt).all()]


def _count(
    column: InstrumentedAttribute[int],
    user_id: int,
    db: Session,
    *,
    accepted_only: bool = False,
    pending_only: bool = False,
) -> int:
    """Count follow rows without loading them.

    Args:
        column: See :func:`_filtered`.
        user_id: The user the rows belong to.
        db: Database session.
        accepted_only: Count only accepted relationships.
        pending_only: Count only pending requests.

    Returns:
        The number of matching relationships.
    """
    stmt = select(func.count()).select_from(_filtered(column, user_id, accepted_only, pending_only).subquery())
    return db.scalar(stmt) or 0


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
    return _page(
        followers_models.Follower.followee_id,
        user_id,
        db,
        page_number=page_number,
        num_records=num_records,
        accepted_only=accepted_only,
    )


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
    ordered by creation time, then ``id``, so paging is stable.

    Args:
        user_id: ID of the user whose following list to retrieve.
        db: Database session.
        page_number: 1-based page number.
        num_records: Page size.
        accepted_only: Exclude pending follow requests when True.

    Returns:
        The follow relationships on this page (empty list if none).
    """
    return _page(
        followers_models.Follower.follower_id,
        user_id,
        db,
        page_number=page_number,
        num_records=num_records,
        accepted_only=accepted_only,
    )


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
    return _page(
        followers_models.Follower.followee_id,
        user_id,
        db,
        page_number=page_number,
        num_records=num_records,
        pending_only=True,
    )


def _advisory_xact_lock(namespace: int, user_id: int, db: Session) -> None:
    """Take a transaction-scoped advisory lock keyed by a user, released on commit or rollback.

    Args:
        namespace: The lock namespace, so unrelated locks on the same user do not collide.
        user_id: The user the lock is keyed by.
        db: Database session.
    """
    db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, :user_id)"),
        {"namespace": namespace, "user_id": user_id},
    )


def lock_pending_requests(user_id: int, db: Session) -> None:
    """Serialise the writers that add a pending request for a user, until the transaction ends.

    A cap read with ``count`` and then enforced by an insert lets concurrent requests each see room
    and all insert, so the writer takes this lock first. It blocks only requests for the same user.

    Args:
        user_id: The user the requests are addressed to.
        db: Database session.
    """
    _advisory_xact_lock(_PENDING_LOCK_NAMESPACE, user_id, db)


def lock_accepted_followees(follower_id: int, db: Session) -> None:
    """Serialise the writers that accept a follow for a follower, until the transaction ends.

    Same reasoning as :func:`lock_pending_requests`, keyed by the follower whose accepted followees
    are capped, so concurrent accepts by different followees cannot each see room and all succeed.

    Args:
        follower_id: The user whose request is being accepted.
        db: Database session.
    """
    _advisory_xact_lock(_ACCEPTED_LOCK_NAMESPACE, follower_id, db)


def count_pending_requests_for_user_id(user_id: int, db: Session) -> int:
    """Count the pending follow requests addressed to a user.

    Args:
        user_id: The user the requests are addressed to.
        db: Database session.

    Returns:
        The number of pending requests.
    """
    return _count(followers_models.Follower.followee_id, user_id, db, pending_only=True)


def count_followers_by_user_id(user_id: int, db: Session, *, accepted_only: bool = False) -> int:
    """Count followers for a user without loading the full rowset.

    Args:
        user_id: ID of the user whose followers to count.
        db: Database session.
        accepted_only: If True, count only accepted relationships.

    Returns:
        Number of follow relationships.
    """
    return _count(followers_models.Follower.followee_id, user_id, db, accepted_only=accepted_only)


def count_following_by_user_id(user_id: int, db: Session, *, accepted_only: bool = False) -> int:
    """Count users a given user is following without loading the rowset.

    Args:
        user_id: ID of the user whose following list to count.
        db: Database session.
        accepted_only: If True, count only accepted relationships.

    Returns:
        Number of follow relationships.
    """
    return _count(followers_models.Follower.follower_id, user_id, db, accepted_only=accepted_only)


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

    Bounded by ``MAX_ACCEPTED_FOLLOWEES``, which the accept path enforces, so callers may use the
    result in an ``IN (...)`` list. Relationships accepted before the cap existed may exceed it;
    they are still returned.

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
) -> followers_constants.FollowStatus:
    """Stage the deletion of a follow relationship between two users.

    Flushes without committing, like :func:`create_follower` and
    :func:`accept_follower`; the service owns the transaction boundary.

    Args:
        user_id: ID of the follower user.
        target_user_id: ID of the user being followed.
        db: Database session.
        status: When given, only delete the row if it is in this state. Declining
            a request must not double as removing an accepted follower.

    Returns:
        The status the deleted row had, read from the delete itself so it cannot
        differ from what was removed.

    Raises:
        NotFoundError: If no matching follower record exists.
    """
    stmt = (
        delete(followers_models.Follower)
        .where(
            followers_models.Follower.follower_id == user_id,
            followers_models.Follower.followee_id == target_user_id,
        )
        .returning(followers_models.Follower.status)
    )
    if status is not None:
        stmt = stmt.where(followers_models.Follower.status == status.value)
    deleted_status = db.execute(stmt).scalar_one_or_none()
    if deleted_status is None:
        raise core_exceptions.NotFoundError("Follower record not found")
    db.flush()
    _invalidate_followee_cache(db)
    return followers_constants.FollowStatus(deleted_status)


def delete_follows_between(
    user_id: int, other_user_id: int, db: Session
) -> list[followers_schema.FollowRelationshipRead]:
    """Stage the deletion of the follow rows between two users, in both directions.

    Args:
        user_id: One of the two users.
        other_user_id: The other user.
        db: Database session.

    Returns:
        The rows that were deleted, with the status each had (empty list when the users were unrelated).
    """
    stmt = (
        delete(followers_models.Follower)
        .where(
            or_(
                and_(
                    followers_models.Follower.follower_id == user_id,
                    followers_models.Follower.followee_id == other_user_id,
                ),
                and_(
                    followers_models.Follower.follower_id == other_user_id,
                    followers_models.Follower.followee_id == user_id,
                ),
            )
        )
        .returning(followers_models.Follower)
        .execution_options(synchronize_session="fetch")
    )
    deleted = [followers_serializers.to_read_schema(row) for row in db.execute(stmt).scalars().all()]
    db.flush()
    _invalidate_followee_cache(db)
    return deleted


def record_decline(follower_id: int, followee_id: int, declined_at: datetime, db: Session) -> None:
    """Stage the time a follow request was declined, replacing an earlier decline of the same pair.

    Declining deletes the pending request first, so two declines of one pair cannot run at once.

    Args:
        follower_id: The requester whose request was declined.
        followee_id: The user who declined it.
        declined_at: When the request was declined.
        db: Database session.
    """
    db.execute(
        delete(followers_models.FollowRequestDecline).where(
            followers_models.FollowRequestDecline.follower_id == follower_id,
            followers_models.FollowRequestDecline.followee_id == followee_id,
        )
    )
    db.add(
        followers_models.FollowRequestDecline(follower_id=follower_id, followee_id=followee_id, declined_at=declined_at)
    )
    db.flush()


def get_last_decline_at(follower_id: int, followee_id: int, db: Session) -> datetime | None:
    """Return when the followee last declined a request from the follower.

    Args:
        follower_id: The requester.
        followee_id: The user the request was addressed to.
        db: Database session.

    Returns:
        The UTC time of the decline, or None when no request was declined.
    """
    stmt = select(followers_models.FollowRequestDecline.declined_at).where(
        followers_models.FollowRequestDecline.follower_id == follower_id,
        followers_models.FollowRequestDecline.followee_id == followee_id,
    )
    return core_timezone.to_utc_aware(db.scalar(stmt))


def is_blocked(blocker_id: int, blocked_id: int, db: Session) -> bool:
    """Tell whether one user has blocked another.

    Args:
        blocker_id: The user who may have blocked.
        blocked_id: The user who may be blocked.
        db: Database session.

    Returns:
        True when the block exists.
    """
    stmt = select(
        exists().where(
            followers_models.FollowerBlock.blocker_id == blocker_id,
            followers_models.FollowerBlock.blocked_id == blocked_id,
        )
    )
    return bool(db.scalar(stmt))


def create_block(blocker_id: int, blocked_id: int, db: Session) -> bool:
    """Stage a block, leaving an existing one as it is.

    Args:
        blocker_id: The user who blocks.
        blocked_id: The user who is blocked; must exist.
        db: Database session.

    Returns:
        True when the block was created, False when it already existed.
    """
    if is_blocked(blocker_id, blocked_id, db):
        return False
    try:
        # A savepoint keeps the caller's transaction usable when a concurrent block wins the unique pair.
        with db.begin_nested():
            db.add(followers_models.FollowerBlock(blocker_id=blocker_id, blocked_id=blocked_id))
            db.flush()
    except IntegrityError as err:
        if core_database.violated_constraint(err) == _UNIQUE_BLOCK_CONSTRAINT:
            return False
        raise
    return True


def delete_block(blocker_id: int, blocked_id: int, db: Session) -> None:
    """Stage the removal of a block.

    Args:
        blocker_id: The user who blocked.
        blocked_id: The user who is blocked.
        db: Database session.

    Raises:
        NotFoundError: If the user has not blocked that user.
    """
    stmt = (
        delete(followers_models.FollowerBlock)
        .where(
            followers_models.FollowerBlock.blocker_id == blocker_id,
            followers_models.FollowerBlock.blocked_id == blocked_id,
        )
        .returning(followers_models.FollowerBlock.id)
    )
    if db.execute(stmt).scalar_one_or_none() is None:
        raise core_exceptions.NotFoundError("Blocked user not found")
    db.flush()


def list_blocked_user_ids(blocker_id: int, db: Session) -> list[int]:
    """List the ids of the users a user has blocked, most recently blocked first.

    Args:
        blocker_id: The user who blocked.
        db: Database session.

    Returns:
        Every blocked user id.
    """
    stmt = (
        select(followers_models.FollowerBlock.blocked_id)
        .where(followers_models.FollowerBlock.blocker_id == blocker_id)
        .order_by(followers_models.FollowerBlock.created_at.desc(), followers_models.FollowerBlock.id.desc())
    )
    return list(db.scalars(stmt).all())
