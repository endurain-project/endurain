"""CRUD operations for users."""

from collections.abc import Collection
from datetime import datetime
from typing import Any
from urllib.parse import unquote

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.etag as core_etag
import core.exceptions as core_exceptions
import core.sanitization as core_sanitization
import modules.users.users.models as users_models
import modules.users.users.schema as users_schema
import modules.users.users.serializers as users_serializers

_DUPLICATE_DETAIL = "Duplicate entry error. Check if email and username are unique"


def _get_user_model_by_id(user_id: int, db: Session) -> users_models.Users:
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


def _filtered(
    stmt,
    show_inactive: bool | None,
    show_email_unverified: bool | None,
    show_pending_approval: bool | None,
    username: str | None = None,
):
    """Apply the optional list filters to a users statement.

    Args:
        stmt: The statement to filter.
        show_inactive: If False, excludes inactive users.
        show_email_unverified: If False, excludes users with unverified emails.
        show_pending_approval: If False, excludes users pending admin approval.
        username: If set, keeps only users whose username contains it.

    Returns:
        The filtered statement.
    """
    if show_inactive is False:
        stmt = stmt.where(users_models.Users.active.is_(True))
    if show_email_unverified is False:
        stmt = stmt.where(users_models.Users.email_verified.is_(True))
    if show_pending_approval is False:
        stmt = stmt.where(users_models.Users.pending_admin_approval.is_(False))
    if username:
        escaped = core_sanitization.escape_like(_normalized_username(username))
        stmt = stmt.where(func.lower(users_models.Users.username).like(f"%{escaped}%", escape="\\"))

    return stmt


def get_all_users(db: Session) -> list[users_schema.UsersRead]:
    """Retrieve all users.

    Args:
        db: Database session.

    Returns:
        All user schemas.
    """
    users = db.execute(select(users_models.Users)).scalars().all()
    return [users_serializers.to_read_schema(user) for user in users]


def get_users_number(
    db: Session,
    show_inactive: bool | None = True,
    show_email_unverified: bool | None = True,
    show_pending_approval: bool | None = True,
    username: str | None = None,
) -> int:
    """Count users matching the optional list filters.

    Args:
        db: Database session.
        show_inactive: If False, excludes inactive users.
        show_email_unverified: If False, excludes users with unverified emails.
        show_pending_approval: If False, excludes users pending admin approval.
        username: If set, counts only users whose username contains it.

    Returns:
        Number of users matching the filters.
    """
    stmt = _filtered(
        select(func.count(users_models.Users.id)), show_inactive, show_email_unverified, show_pending_approval, username
    )
    return db.execute(stmt).scalar_one()


def get_users_with_pagination(
    db: Session,
    page_number: int | None = None,
    num_records: int | None = None,
    show_inactive: bool | None = True,
    show_email_unverified: bool | None = True,
    show_pending_approval: bool | None = True,
    username: str | None = None,
) -> list[users_schema.UsersRead]:
    """Retrieve a page of users, ordered by username, with optional filters.

    Args:
        db: Database session.
        page_number: The 1-indexed page; pagination is skipped when it or ``num_records`` is None.
        num_records: The number of records per page.
        show_inactive: If False, excludes inactive users.
        show_email_unverified: If False, excludes users with unverified emails.
        show_pending_approval: If False, excludes users pending admin approval.
        username: If set, keeps only users whose username contains it.

    Returns:
        The users matching the filters.
    """
    stmt = _filtered(select(users_models.Users), show_inactive, show_email_unverified, show_pending_approval, username)
    stmt = stmt.order_by(users_models.Users.username)

    if page_number is not None and num_records is not None:
        stmt = stmt.offset((page_number - 1) * num_records).limit(num_records)

    return [users_serializers.to_read_schema(user) for user in db.execute(stmt).scalars().all()]


def _normalized_username(username: str) -> str:
    """Decode and lower-case a username as it arrives in a URL.

    Args:
        username: The raw username.

    Returns:
        The normalized username.
    """
    return unquote(username).replace("+", " ").lower()


def get_user_by_username(username: str, db: Session) -> users_schema.UsersRead | None:
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


def search_active_users_by_username(username: str, limit: int, db: Session) -> list[users_schema.UsersRead]:
    """Retrieve the active users whose username contains the search term.

    Args:
        username: The partial username to search for.
        limit: The most users to return.
        db: Database session.

    Returns:
        The matching users, ordered by username.
    """
    stmt = (
        _filtered(select(users_models.Users), False, True, True, username)
        .order_by(users_models.Users.username)
        .limit(limit)
    )
    return [users_serializers.to_read_schema(user) for user in db.execute(stmt).scalars().all()]


def get_user_by_email(email: str, db: Session) -> users_schema.UsersRead | None:
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


def get_user_by_id(user_id: int, db: Session) -> users_schema.UsersRead | None:
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


def get_users_by_ids(user_ids: Collection[int], db: Session) -> list[users_schema.UsersRead]:
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


def get_users_admin(db: Session) -> list[users_schema.UsersRead]:
    """Retrieve all admin users.

    Args:
        db: Database session.

    Returns:
        The admin user schemas.
    """
    stmt = select(users_models.Users).where(users_models.Users.access_type == users_schema.UserAccessType.ADMIN.value)
    return [users_serializers.to_read_schema(user) for user in db.execute(stmt).scalars().all()]


def get_photo_key(user_id: int, db: Session) -> str | None:
    """Return the storage key of a user's photo, as stored on the row.

    Args:
        user_id: The user to look up.
        db: Database session.

    Returns:
        The key, or None if the user has no photo or does not exist.
    """
    stmt = select(users_models.Users.photo_path).where(users_models.Users.id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def replace_photo_key(user_id: int, photo_key: str | None, db: Session) -> str | None:
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


def lock_active_admin_ids(db: Session) -> list[int]:
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


def get_stored_photo_keys(db: Session) -> list[tuple[int, str | None]]:
    """Return every user's raw stored photo value (migration use only).

    The read schema resolves ``photo_path`` into a signed URL, so a migration
    that needs the value actually on the row cannot go through
    :func:`get_all_users`. Scalars are returned rather than model instances so
    no ORM object leaves this module.

    Args:
        db: Database session.

    Returns:
        ``(user_id, photo_path)`` pairs.
    """
    rows = db.execute(select(users_models.Users.id, users_models.Users.photo_path)).all()
    return [(row[0], row[1]) for row in rows]


def create_user(fields: dict[str, Any], db: Session) -> users_schema.UsersRead:
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
    user_id: int, changes: dict[str, Any], db: Session, *, if_match: str | None = None
) -> users_schema.UsersRead:
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

    try:
        db.flush()
        db.refresh(db_user)
    except IntegrityError as err:
        raise core_exceptions.ConflictError(_DUPLICATE_DETAIL) from err

    return users_serializers.to_read_schema(db_user)


def stage_deletion_request(user_id: int, db: Session) -> None:
    """Stage the deactivation of a user and the marker that its deletion is queued (flushed, not committed).

    Args:
        user_id: ID of the user being deleted.
        db: Database session.

    Raises:
        NotFoundError: If the user does not exist.
    """
    db_user = _get_user_model_by_id(user_id, db)
    db_user.active = False
    db_user.deletion_requested_at = func.now()
    db_user.deletion_attempts = 0
    db.flush()


def list_stalled_deletion_ids(
    requested_before: datetime, max_attempts: int, after_id: int, limit: int, db: Session
) -> list[int]:
    """Return the ids of users whose queued deletion has not finished, oldest id first.

    Args:
        requested_before: Only deletions queued before this instant.
        max_attempts: Only users the sweep has queued fewer times than this.
        after_id: Return only ids above this, so a pass pages through the table.
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
            users_models.Users.id > after_id,
        )
        .order_by(users_models.Users.id)
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def record_deletion_attempt(user_id: int, db: Session) -> int | None:
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


def delete_user(user_id: int, db: Session) -> None:
    """Stage the deletion of a user row (flushed, not committed).

    Args:
        user_id: ID of the user to delete.
        db: Database session.

    Raises:
        NotFoundError: If the user does not exist.
    """
    db.delete(_get_user_model_by_id(user_id, db))
    db.flush()
