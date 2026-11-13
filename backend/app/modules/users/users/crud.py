"""CRUD operations for users."""

import uuid
from collections.abc import Collection, Mapping, Sequence
from datetime import datetime

from sqlalchemy import Select, exists, func, select, text
from sqlalchemy import update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import core.sanitization as core_sanitization
import modules.users.users.models as users_models
import modules.users.users.schema as users_schema
import modules.users.users.serializers as users_serializers

_DUPLICATE_DETAIL = "Duplicate entry error. Check if email and username are unique"

#: Advisory-lock key serializing the creation of the first administrator. It differs from the migration lock key
#: (``_MIGRATION_LOCK_KEY`` in ``migrations/startup.py``), and the single-key form lives apart from the two-key
#: namespaces the followers use.
_FIRST_ADMIN_LOCK_KEY = 7_203_419_002


def _get_user_model_by_id(user_id: uuid.UUID, db: Session) -> users_models.Users:
    """Retrieve a mapped user ORM row by ID.

    Args:
        user_id: User ID to search for.
        db: Database session.

    Returns:
        The mapped ``Users`` ORM instance.

    Raises:
        NotFoundError: If the user does not exist.
    """
    stmt = select(users_models.Users).where(users_models.Users.id == user_id)
    db_user = db.execute(stmt).scalar_one_or_none()
    if db_user is None:
        raise core_exceptions.NotFoundError("User not found")

    return db_user


def _filtered[RowT: tuple[object, ...]](
    stmt: Select[RowT],
    *,
    active: bool | None = None,
    email_verified: bool | None = None,
    pending_approval: bool | None = None,
    username: str | None = None,
    username_contains: str | None = None,
    external_auth: bool | None = None,
    linked_user_ids: Select[tuple[uuid.UUID]] | None = None,
    exclude_user_ids: Collection[uuid.UUID] = (),
) -> Select[RowT]:
    """Apply the optional list filters to a users statement.

    Args:
        stmt: The statement to filter.
        active: If set, keeps only users whose active flag equals it.
        email_verified: If set, keeps only users whose email verification flag equals it.
        pending_approval: If set, keeps only users whose pending-approval flag equals it.
        username: If set, keeps only the user with this exact username.
        username_contains: If set, keeps only users whose username contains it.
        external_auth: If set, keeps only users who are (True) or are not (False) in ``linked_user_ids``.
        linked_user_ids: The users who have an identity-provider link; required with ``external_auth``.
        exclude_user_ids: Users to leave out.

    Returns:
        The filtered statement.
    """
    if active is not None:
        stmt = stmt.where(users_models.Users.active.is_(active))
    if email_verified is not None:
        stmt = stmt.where(users_models.Users.email_verified.is_(email_verified))
    if pending_approval is not None:
        stmt = stmt.where(users_models.Users.pending_admin_approval.is_(pending_approval))
    if username:
        stmt = stmt.where(users_models.Users.username == _normalized_username(username))
    if username_contains:
        escaped = core_sanitization.escape_like(_normalized_username(username_contains))
        stmt = stmt.where(func.lower(users_models.Users.username).like(f"%{escaped}%", escape="\\"))
    if external_auth is not None and linked_user_ids is not None:
        linked = users_models.Users.id.in_(linked_user_ids)
        stmt = stmt.where(linked if external_auth else ~linked)
    if exclude_user_ids:
        stmt = stmt.where(users_models.Users.id.not_in(exclude_user_ids))

    return stmt


def get_users_number(
    db: Session,
    *,
    active: bool | None = None,
    email_verified: bool | None = None,
    pending_approval: bool | None = None,
    username: str | None = None,
    username_contains: str | None = None,
    external_auth: bool | None = None,
    linked_user_ids: Select[tuple[uuid.UUID]] | None = None,
    exclude_user_ids: Collection[uuid.UUID] = (),
) -> int:
    """Count users matching the optional list filters.

    Args:
        db: Database session.
        active: If set, counts only users whose active flag equals it.
        email_verified: If set, counts only users whose email verification flag equals it.
        pending_approval: If set, counts only users whose pending-approval flag equals it.
        username: If set, counts only the user with this exact username.
        username_contains: If set, counts only users whose username contains it.
        external_auth: If set, counts only users who are (True) or are not (False) in ``linked_user_ids``.
        linked_user_ids: The users who have an identity-provider link; required with ``external_auth``.
        exclude_user_ids: Users to leave out of the count.

    Returns:
        Number of users matching the filters.
    """
    stmt = _filtered(
        select(func.count(users_models.Users.id)),
        active=active,
        email_verified=email_verified,
        pending_approval=pending_approval,
        username=username,
        username_contains=username_contains,
        external_auth=external_auth,
        linked_user_ids=linked_user_ids,
        exclude_user_ids=exclude_user_ids,
    )
    return db.execute(stmt).scalar_one()


def get_users_with_pagination(
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    *,
    active: bool | None = None,
    email_verified: bool | None = None,
    pending_approval: bool | None = None,
    username: str | None = None,
    username_contains: str | None = None,
    external_auth: bool | None = None,
    linked_user_ids: Select[tuple[uuid.UUID]] | None = None,
    exclude_user_ids: Collection[uuid.UUID] = (),
) -> list[users_schema.UserRead]:
    """Retrieve a page of users, ordered by username, with optional filters.

    Args:
        db: Database session.
        page_number: The 1-indexed page; pagination is skipped when it or ``num_records`` is None.
        num_records: The number of records per page.
        active: If set, keeps only users whose active flag equals it.
        email_verified: If set, keeps only users whose email verification flag equals it.
        pending_approval: If set, keeps only users whose pending-approval flag equals it.
        username: If set, keeps only the user with this exact username.
        username_contains: If set, keeps only users whose username contains it.
        external_auth: If set, keeps only users who are (True) or are not (False) in ``linked_user_ids``.
        linked_user_ids: The users who have an identity-provider link; required with ``external_auth``.
        exclude_user_ids: Users to leave out.

    Returns:
        The users matching the filters.
    """
    stmt = _filtered(
        select(users_models.Users),
        active=active,
        email_verified=email_verified,
        pending_approval=pending_approval,
        username=username,
        username_contains=username_contains,
        external_auth=external_auth,
        linked_user_ids=linked_user_ids,
        exclude_user_ids=exclude_user_ids,
    )
    stmt = stmt.order_by(users_models.Users.username)

    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

    return [users_serializers.to_read_schema(user) for user in db.execute(stmt).scalars().all()]


def _normalized_username(username: str) -> str:
    """Lower-case a username that the framework has already URL-decoded.

    Args:
        username: The username from the path or query string.

    Returns:
        The normalized username.
    """
    return username.lower()


def get_user_by_username(username: str, db: Session) -> users_schema.UserRead | None:
    """Retrieve a user by exact username.

    Args:
        username: Username to search for.
        db: Database session.

    Returns:
        The user, or None if there is none.
    """
    stmt = select(users_models.Users).where(users_models.Users.username == _normalized_username(username))
    user = db.execute(stmt).scalar_one_or_none()
    return users_serializers.to_read_schema(user) if user else None


def get_user_by_email(email: str, db: Session) -> users_schema.UserRead | None:
    """Retrieve a user by email address.

    Args:
        email: Email address to search for (case-insensitive).
        db: Database session.

    Returns:
        The user, or None if there is none.
    """
    stmt = select(users_models.Users).where(users_models.Users.email == email.lower())
    user = db.execute(stmt).scalar_one_or_none()
    return users_serializers.to_read_schema(user) if user else None


def get_user_by_id(user_id: uuid.UUID, db: Session) -> users_schema.UserRead | None:
    """Retrieve a user by ID.

    Args:
        user_id: User ID to search for.
        db: Database session.

    Returns:
        The user, or None if there is none.
    """
    stmt = select(users_models.Users).where(users_models.Users.id == user_id)
    user = db.execute(stmt).scalar_one_or_none()
    return users_serializers.to_read_schema(user) if user else None


def get_users_by_ids(user_ids: Collection[uuid.UUID], db: Session) -> list[users_schema.UserRead]:
    """Retrieve several users by ID in one query.

    Args:
        user_ids: IDs to look up; repeated IDs are read once.
        db: Database session.

    Returns:
        The users that exist, in no particular order. An empty list when no IDs are given, without
        querying.
    """
    if not user_ids:
        return []
    stmt = select(users_models.Users).where(users_models.Users.id.in_(set(user_ids)))
    return [users_serializers.to_read_schema(user) for user in db.execute(stmt).scalars().all()]


def get_users_admin(db: Session) -> list[users_schema.UserRead]:
    """Retrieve all admin users.

    Args:
        db: Database session.

    Returns:
        The admin user schemas.
    """
    stmt = select(users_models.Users).where(users_models.Users.access_type == users_schema.UserAccessType.ADMIN.value)
    return [users_serializers.to_read_schema(user) for user in db.execute(stmt).scalars().all()]


def get_photo_key(user_id: uuid.UUID, db: Session) -> str | None:
    """Return the storage key of a user's photo, as stored on the row.

    Args:
        user_id: The user to look up.
        db: Database session.

    Returns:
        The key, or None if the user has no photo or does not exist.
    """
    stmt = select(users_models.Users.photo_path).where(users_models.Users.id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def get_photo_keys_by_user_ids(user_ids: list[uuid.UUID], db: Session) -> dict[uuid.UUID, str]:
    """Return the photo each of the given users names, as stored on the row.

    Args:
        user_ids: The users to look up.
        db: Database session.

    Returns:
        The stored photo by user id; a user with no photo, or that does not exist, is left out.
    """
    stmt = select(users_models.Users.id, users_models.Users.photo_path).where(
        users_models.Users.id.in_(user_ids), users_models.Users.photo_path.is_not(None)
    )
    return {user_id: photo for user_id, photo in db.execute(stmt).all()}


def replace_photo_key(user_id: uuid.UUID, photo_key: str | None, db: Session) -> str | None:
    """Row-lock a user, set their stored photo key, and return the key it replaced (flushed, not committed).

    Concurrent photo changes for one user queue on the lock, so each sees exactly the key it
    replaced and no change can mistake another's new key for a leftover.

    Args:
        user_id: The user to update.
        photo_key: The new ``StorageProvider`` key, or None to clear the photo.
        db: Database session.

    Returns:
        The key the row held before, or None if there was none.

    Raises:
        NotFoundError: If the user does not exist.
    """
    stmt = select(users_models.Users).where(users_models.Users.id == user_id).with_for_update()
    db_user = db.execute(stmt).scalar_one_or_none()
    if db_user is None:
        raise core_exceptions.NotFoundError("User not found")

    previous = db_user.photo_path
    db_user.photo_path = photo_key
    db.flush()
    return previous


def replace_photo_keys(changes: Sequence[tuple[uuid.UUID, str, str]], db: Session) -> None:
    """Stage new photo keys, each only where the user still holds the key it was read with.

    A Core ``UPDATE`` that leaves ``version`` alone; the caller commits.

    Args:
        changes: ``(user id, current key, new key)`` triples.
        db: Database session.
    """
    for user_id, old_key, new_key in changes:
        db.execute(
            sa_update(users_models.Users)
            .where(users_models.Users.id == user_id, users_models.Users.photo_path == old_key)
            .values(photo_path=new_key)
        )
    db.flush()


def any_user_exists(db: Session) -> bool:
    """Tell whether at least one user exists.

    Args:
        db: Database session.

    Returns:
        True when the users table holds a row.
    """
    return bool(db.execute(select(exists().select_from(users_models.Users))).scalar_one())


def lock_first_admin_creation(db: Session) -> None:
    """Serialize the creation of the first administrator until the transaction ends.

    An empty users table has no row to lock, so concurrent onboarding requests would each see no user and each
    insert one. The transaction-scoped advisory lock makes the second wait for the first to commit or roll back,
    and it then sees the user.

    Args:
        db: Database session.
    """
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _FIRST_ADMIN_LOCK_KEY})


def lock_active_admin_ids(db: Session) -> list[uuid.UUID]:
    """Row-lock the active administrators, in id order, and return their ids.

    Two concurrent requests that each remove a different administrator would otherwise both see
    "another one remains" and leave none. The lock makes the second wait for the first to commit,
    and it then counts what is really left.

    Args:
        db: Database session.

    Returns:
        The ids of the active admin users.
    """
    stmt = (
        select(users_models.Users.id)
        .where(
            users_models.Users.access_type == users_schema.UserAccessType.ADMIN.value,
            users_models.Users.active.is_(True),
        )
        .order_by(users_models.Users.id)
        .with_for_update()
    )
    return list(db.execute(stmt).scalars().all())


def get_stored_photo_keys(db: Session) -> list[tuple[uuid.UUID, str | None]]:
    """Return every user's raw stored photo value (migration use only).

    The read schema resolves ``photo_path`` into a signed URL, so a migration
    that needs the value actually on the row cannot go through the read schemas.
    Scalars are returned rather than model instances so no ORM object leaves
    this module.

    Args:
        db: Database session.

    Returns:
        ``(user_id, photo_path)`` pairs.
    """
    rows = db.execute(select(users_models.Users.id, users_models.Users.photo_path)).all()
    return [(row[0], row[1]) for row in rows]


def create_user(fields: Mapping[str, object], db: Session) -> users_schema.UserRead:
    """Stage a new user row (flushed, not committed).

    Args:
        fields: The column values of the new user, already normalized.
        db: Database session.

    Returns:
        The created user.

    Raises:
        ConflictError: If the username or email is already taken.
    """
    db_user = users_models.Users(**fields)
    try:
        db.add(db_user)
        db.flush()
        db.refresh(db_user)
    except IntegrityError as err:
        raise core_exceptions.ConflictError(_DUPLICATE_DETAIL) from err

    return users_serializers.to_read_schema(db_user)


def update_user(
    user_id: uuid.UUID, changes: Mapping[str, object], db: Session, *, if_match: str | None = None
) -> users_schema.UserRead:
    """Stage column changes on a user (flushed, not committed).

    Args:
        user_id: ID of the user to update.
        changes: The column values to set. Names that are read-only properties on the model
            are skipped.
        db: Database session.
        if_match: The ``If-Match`` precondition of a client edit, checked against the row this function
            edits. ``None`` for a system writer, which the flush's ``version_id_col`` guard still holds to
            the version it loaded.

    Returns:
        The updated user.

    Raises:
        NotFoundError: If the user does not exist.
        ConflictError: If the username or email is already taken.
        PreconditionFailedError: When ``if_match`` does not name the row's version.
    """
    db_user = _get_user_model_by_id(user_id, db)
    if if_match is not None:
        core_etag.require_if_match(if_match, db_user.version, "user")

    was_active = db_user.active
    for key, value in changes.items():
        # Response-only fields are excluded by the caller; this guards any computed
        # property added to the model later.
        class_attr = getattr(type(db_user), key, None)
        if isinstance(class_attr, property) and class_attr.fset is None:
            continue
        setattr(db_user, key, value)
    if changes.get("active") is True:
        # Reactivating an account cancels a deletion queued for it, or the sweep would carry it out.
        db_user.deletion_requested_at = None
        db_user.deletion_attempts = 0
        db_user.deactivated_at = None
    elif changes.get("active") is False and was_active:
        db_user.deactivated_at = func.now()

    try:
        db.flush()
        db.refresh(db_user)
    except IntegrityError as err:
        raise core_exceptions.ConflictError(_DUPLICATE_DETAIL) from err

    return users_serializers.to_read_schema(db_user)


def approve_pending_user(user_id: uuid.UUID, db: Session) -> bool:
    """Activate a user who is awaiting approval (flushed, not committed).

    The row is locked while its state is read, so the check and the write cannot be split by a concurrent
    deactivation or deletion request.

    Args:
        user_id: ID of the user to approve.
        db: Database session.

    Returns:
        True when the user was pending approval, not deactivated and not queued for deletion, and is now
        approved and active. False when the user is in any other state, which is left untouched.

    Raises:
        NotFoundError: If the user does not exist.
    """
    stmt = select(users_models.Users).where(users_models.Users.id == user_id).with_for_update()
    db_user = db.execute(stmt).scalar_one_or_none()
    if db_user is None:
        raise core_exceptions.NotFoundError("User not found")
    if (
        not db_user.pending_admin_approval
        or db_user.deactivated_at is not None
        or db_user.deletion_requested_at is not None
    ):
        return False
    db_user.pending_admin_approval = False
    db_user.active = True
    db.flush()
    return True


def lock_unverified_sign_ups(
    created_before: datetime, held_user_ids: Sequence[Select[tuple[uuid.UUID]]], limit: int, db: Session
) -> list[uuid.UUID]:
    """Lock up to ``limit`` unverified self sign-ups created before ``created_before`` and return their ids.

    A row qualifies while it is inactive, its address is unverified and no administrator or deletion request
    deactivated it, and none of the ``held_user_ids`` queries names it. Rows another transaction holds are skipped,
    so a verification in flight wins. The exclusions are read again once the rows are locked, so a change that
    committed in between keeps its row out.

    Args:
        created_before: Only accounts created before this instant qualify.
        held_user_ids: Queries for the ids of the users that must be kept, such as those with a credential.
        limit: The most rows to lock.
        db: Database session.

    Returns:
        The ids of the locked rows, which stay locked until the transaction ends.
    """
    model = users_models.Users
    stmt = (
        select(model.id)
        .where(
            model.created_at < created_before,
            model.active.is_(False),
            model.email_verified.is_(False),
            model.deactivated_at.is_(None),
            model.deletion_requested_at.is_(None),
            *(model.id.not_in(held) for held in held_user_ids),
        )
        .order_by(model.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    locked = list(db.execute(stmt).scalars().all())
    if not locked:
        return []
    recheck = select(model.id).where(model.id.in_(locked), *(model.id.not_in(held) for held in held_user_ids))
    return list(db.execute(recheck.order_by(model.id)).scalars().all())


def is_deactivated(user_id: uuid.UUID, db: Session) -> bool:
    """Tell whether an administrator or a deletion request deactivated a user.

    Args:
        user_id: ID of the user.
        db: Database session.

    Returns:
        True when the account carries a deactivation time. False for an active account and for a sign-up
        that is not yet verified or approved.

    Raises:
        NotFoundError: If the user does not exist.
    """
    return _get_user_model_by_id(user_id, db).deactivated_at is not None


def was_created_after(user_id: uuid.UUID, moment: datetime, db: Session) -> bool:
    """Tell whether a user's account was created after a moment.

    Args:
        user_id: ID of the user.
        moment: The instant to compare the creation time with.
        db: Database session.

    Returns:
        True when the account was created after the moment. False when it was created at or before it, and when
        the user does not exist.
    """
    model = users_models.Users
    stmt = select(exists().where(model.id == user_id, model.created_at > moment))
    return bool(db.execute(stmt).scalar_one())


def stage_deletion_request(user_id: uuid.UUID, db: Session) -> None:
    """Stage the deactivation of a user and the marker that its deletion is queued (flushed, not committed).

    Args:
        user_id: ID of the user being deleted.
        db: Database session.

    Raises:
        NotFoundError: If the user does not exist.
    """
    db_user = _get_user_model_by_id(user_id, db)
    db_user.active = False
    db_user.deactivated_at = func.now()
    db_user.deletion_requested_at = func.now()
    db_user.deletion_attempts = 0
    db.flush()


def list_stalled_deletion_ids(
    requested_before: datetime, max_attempts: int, after_id: uuid.UUID | None, limit: int, db: Session
) -> list[uuid.UUID]:
    """Return the ids of users whose queued deletion has not finished, oldest id first.

    Args:
        requested_before: Only deletions queued before this instant.
        max_attempts: Only users the sweep has queued fewer times than this.
        after_id: Return only ids above this, so a pass pages through the table; None starts from the first.
        limit: The most ids to return.
        db: Database session.

    Returns:
        The user ids, ascending.
    """
    stmt = (
        select(users_models.Users.id)
        .where(
            users_models.Users.deletion_requested_at < requested_before,
            users_models.Users.deletion_attempts < max_attempts,
        )
        .order_by(users_models.Users.id)
        .limit(limit)
    )
    if after_id is not None:
        stmt = stmt.where(users_models.Users.id > after_id)
    return list(db.scalars(stmt).all())


def record_deletion_attempt(user_id: uuid.UUID, db: Session) -> int | None:
    """Stage one more automatic attempt at a user's deletion (flushed, not committed).

    Args:
        user_id: ID of the user being deleted.
        db: Database session.

    Returns:
        The attempts made so far including this one, or None when the user is gone or no longer queued
        for deletion (an administrator reactivated the account).
    """
    stmt = select(users_models.Users).where(users_models.Users.id == user_id).with_for_update()
    db_user = db.execute(stmt).scalar_one_or_none()
    if db_user is None or db_user.deletion_requested_at is None:
        return None
    db_user.deletion_attempts += 1
    db.flush()
    return db_user.deletion_attempts


def get_deletion_attempts(user_id: uuid.UUID, db: Session) -> int | None:
    """Return how many times the sweep has queued a user's deletion again.

    Args:
        user_id: ID of the user being deleted.
        db: Database session.

    Returns:
        The count, or None when the user does not exist.
    """
    stmt = select(users_models.Users.deletion_attempts).where(users_models.Users.id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def is_deletion_cancelled(user_id: uuid.UUID, db: Session) -> bool:
    """Tell whether an administrator reactivated a user whose deletion was queued.

    The row is locked until the caller's transaction ends, so a reactivation cannot slip in between
    this answer and the deletion it guards.

    Args:
        user_id: ID of the user being deleted.
        db: Database session.

    Returns:
        True when the user exists and is no longer queued for deletion. False when the deletion should
        go on, including when the user is already gone.
    """
    stmt = select(users_models.Users).where(users_models.Users.id == user_id).with_for_update()
    db_user = db.execute(stmt).scalar_one_or_none()
    return db_user is not None and db_user.deletion_requested_at is None


def delete_user(user_id: uuid.UUID, db: Session) -> None:
    """Stage the deletion of a user row (flushed, not committed).

    Args:
        user_id: ID of the user to delete.
        db: Database session.

    Raises:
        NotFoundError: If the user does not exist.
    """
    db.delete(_get_user_model_by_id(user_id, db))
    db.flush()
