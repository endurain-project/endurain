"""CRUD helpers for the ``users_mfa`` 1:1 companion table."""

from sqlalchemy import select
from sqlalchemy.orm import Session

import core.decorators as core_decorators
import modules.auth.mfa.models as auth_mfa_models


@core_decorators.handle_db_errors
def get_user_mfa_row(user_id: int, db: Session) -> auth_mfa_models.UsersMFA | None:
    """
    Retrieve the ``users_mfa`` row for a user.

    Args:
        user_id: ID of the user to fetch the MFA row for.
        db: SQLAlchemy database session.

    Returns:
        The user's ``UsersMFA`` row, or None if no row exists.

    Raises:
        HTTPException: 500 if a database error occurs.
    """
    stmt = select(auth_mfa_models.UsersMFA).where(auth_mfa_models.UsersMFA.user_id == user_id)
    return db.execute(stmt).scalar_one_or_none()


@core_decorators.handle_db_errors
def get_mfa_enabled_for_users(user_ids: list[int], db: Session) -> dict[int, bool]:
    """
    Return MFA-enabled state per user in a single query.

    Mirrors :func:`auth.mfa.service.is_mfa_enabled_for_user` semantics
    (a row with ``mfa_enabled`` set and a stored secret) but resolves
    many users at once so callers avoid an N+1 lookup.

    Args:
        user_ids: List of user IDs to resolve MFA state for.
        db: SQLAlchemy database session.

    Returns:
        Dict mapping user_id to ``True`` for users with MFA enabled.
        Users without MFA are absent from the result (callers should
        use ``.get(user_id, False)``).

    Raises:
        HTTPException: 500 if a database error occurs.
    """
    if not user_ids:
        return {}
    stmt = select(auth_mfa_models.UsersMFA.user_id).where(
        auth_mfa_models.UsersMFA.user_id.in_(user_ids),
        auth_mfa_models.UsersMFA.mfa_enabled.is_(True),
        auth_mfa_models.UsersMFA.mfa_secret.is_not(None),
    )
    return {row.user_id: True for row in db.execute(stmt).all()}


@core_decorators.handle_db_errors
def update_user_mfa(user_id: int, db: Session, encrypted_secret: str | None = None) -> None:
    """
    Update a user's MFA settings in the ``users_mfa`` table.

    Args:
        user_id: ID of user to update MFA for.
        db: SQLAlchemy database session.
        encrypted_secret: Encrypted MFA secret.
            If None, disables MFA.

    Returns:
        None

    Raises:
        HTTPException: 500 if database error occurs.
    """
    mfa_enabled = bool(encrypted_secret)
    mfa_secret_value = encrypted_secret if encrypted_secret else None

    stmt = select(auth_mfa_models.UsersMFA).where(auth_mfa_models.UsersMFA.user_id == user_id)
    mfa_row = db.execute(stmt).scalar_one_or_none()
    if mfa_row is None:
        # Row may be missing if the backfill migration has
        # not yet created one for this user; create it on
        # first write.
        mfa_row = auth_mfa_models.UsersMFA(
            user_id=user_id,
            mfa_enabled=mfa_enabled,
            mfa_secret=mfa_secret_value,
        )
        db.add(mfa_row)
    else:
        mfa_row.mfa_enabled = mfa_enabled
        mfa_row.mfa_secret = mfa_secret_value

    db.commit()


@core_decorators.handle_db_errors
def create_users_mfa_row(user_id: int, db: Session) -> auth_mfa_models.UsersMFA:
    """
    Create the default ``users_mfa`` row for a newly created user.

    MFA is disabled by default; the row exists so that the 1:1
    invariant between ``users`` and ``users_mfa`` holds for every
    user without relying on the defensive create-on-update branch
    in ``modules.auth.mfa.crud.update_user_mfa``.

    Args:
        user_id: ID of the user to create the row for.
        db: SQLAlchemy database session.

    Returns:
        The persisted ``UsersMFA`` row.

    Raises:
        HTTPException: 500 if the database operation fails.
    """
    mfa_row = auth_mfa_models.UsersMFA(
        user_id=user_id,
        mfa_enabled=False,
        mfa_secret=None,
    )
    db.add(mfa_row)
    db.commit()
    db.refresh(mfa_row)
    return mfa_row
