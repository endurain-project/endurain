"""Users as the application stores them, for tests on the real database."""

import uuid
from datetime import UTC, datetime
from functools import cache

from sqlalchemy.orm import Session

import modules.auth.credentials.integration_service as credentials_integration
import modules.users.users.crud as users_crud
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service

#: The password of every user made with ``with_password=True``.
PASSWORD = "Factory-Password-1234!"


@cache
def _password_hash() -> str:
    """Hash :data:`PASSWORD` once per process: a real Argon2 hash, without paying for one per user."""
    return credentials_integration.get_password_hasher().hash_password(PASSWORD)


def make_user(
    db: Session,
    *,
    access_type: users_schema.UserAccessType = users_schema.UserAccessType.REGULAR,
    active: bool = True,
    email_verified: bool = True,
    pending_admin_approval: bool = False,
    with_password: bool = True,
    **fields: object,
) -> users_schema.UserRead:
    """Stage a user with the rows every new account starts with (flushed, not committed).

    The row and the default data come from the same functions account creation uses; no audit row is staged, so a
    test's audit assertions see only what the code under test records.

    Args:
        db: Database session.
        access_type: The account's access tier.
        active: Whether the account is active; an inactive one is stamped deactivated now.
        email_verified: Whether the address is proven.
        pending_admin_approval: Whether the account waits for an administrator's approval.
        with_password: Whether the account has a local credential, with the password :data:`PASSWORD`.
        **fields: Other column values, which override the unique defaults (``name``, ``username``, ``email``).

    Returns:
        The staged user.
    """
    unique = uuid.uuid4().hex[:12]
    values: dict[str, object] = {
        "name": f"User {unique}",
        "username": f"user-{unique}",
        "email": f"user-{unique}@example.com",
        "preferred_language": "en",
        "access_type": access_type.value,
        "active": active,
        "email_verified": email_verified,
        "pending_admin_approval": pending_admin_approval,
    }
    if not active:
        values["deactivated_at"] = datetime.now(UTC)
    values.update(fields)
    user = users_crud.create_user(values, db)
    if with_password:
        credentials_integration.set_local_password_hash(user.id, _password_hash(), db, change_required=False)
    users_service._stage_default_data(user.id, db)
    db.flush()
    return user


def make_admin(db: Session, **fields: object) -> users_schema.UserRead:
    """Stage an active administrator (flushed, not committed); see :func:`make_user`."""
    return make_user(db, access_type=users_schema.UserAccessType.ADMIN, **fields)
