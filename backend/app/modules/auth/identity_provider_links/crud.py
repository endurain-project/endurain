"""Persistence operations for identity-provider links."""

from datetime import UTC, datetime

from sqlalchemy import Select, delete, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.database as core_database
import core.exceptions as core_exceptions
import core.key_rotation as core_key_rotation
import modules.auth.identity_provider_links.contracts as identity_link_contracts
import modules.auth.identity_provider_links.models as identity_link_models
import modules.auth.identity_provider_links.serializers as identity_link_serializers


def check_user_identity_providers_by_idp_id(idp_id: int, db: Session) -> bool:
    """Return whether an identity provider has linked users."""
    statement = select(exists().where(identity_link_models.IdentityLink.idp_id == idp_id))
    return bool(db.execute(statement).scalar())


def get_user_identity_providers_by_user_id(user_id: int, db: Session) -> list[identity_link_contracts.IdentityLinkRead]:
    """Return the user's identity-provider links."""
    statement = select(identity_link_models.IdentityLink).where(identity_link_models.IdentityLink.user_id == user_id)
    rows = db.execute(statement).scalars().all()
    return [identity_link_serializers.to_read_schema(row) for row in rows]


def get_identity_links_page(
    user_id: int,
    db: Session,
    *,
    limit: int,
    offset: int,
) -> list[identity_link_contracts.IdentityLinkRead]:
    """Return one window of the user's links, oldest first with the id as tiebreak."""
    model = identity_link_models.IdentityLink
    stmt = select(model).where(model.user_id == user_id).order_by(model.linked_at, model.id).limit(limit).offset(offset)
    rows = db.execute(stmt).scalars()
    return [identity_link_serializers.to_read_schema(row) for row in rows]


def count_identity_links(user_id: int, db: Session) -> int:
    """Return how many links the user has."""
    model = identity_link_models.IdentityLink
    return db.execute(select(func.count(model.id)).where(model.user_id == user_id)).scalar_one()


def get_user_identity_provider_by_user_id_and_idp_id(
    user_id: int,
    idp_id: int,
    db: Session,
) -> identity_link_contracts.IdentityLinkRead | None:
    """Return a link for a user and identity provider."""
    statement = select(identity_link_models.IdentityLink).where(
        identity_link_models.IdentityLink.user_id == user_id,
        identity_link_models.IdentityLink.idp_id == idp_id,
    )
    row = db.execute(statement).scalar_one_or_none()
    return identity_link_serializers.to_read_schema(row) if row is not None else None


def get_user_identity_provider_by_subject_and_idp_id(
    idp_id: int,
    idp_subject: str,
    db: Session,
) -> identity_link_contracts.IdentityLinkRead | None:
    """Return a link matching an identity provider and subject."""
    statement = select(identity_link_models.IdentityLink).where(
        identity_link_models.IdentityLink.idp_id == idp_id,
        identity_link_models.IdentityLink.idp_subject == idp_subject,
    )
    row = db.execute(statement).scalar_one_or_none()
    return identity_link_serializers.to_read_schema(row) if row is not None else None


def create_user_identity_provider(
    user_id: int,
    idp_id: int,
    idp_subject: str,
    db: Session,
) -> identity_link_contracts.IdentityLinkRead:
    """Stage a user-to-provider link, translating unique-key races."""
    row = identity_link_models.IdentityLink(
        user_id=user_id,
        idp_id=idp_id,
        idp_subject=idp_subject,
        last_login=func.now(),
    )
    db.flush()
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as err:
        raise core_exceptions.ConflictError("Identity provider already linked") from err
    return identity_link_serializers.to_read_schema(row)


def update_user_identity_provider_last_login(
    user_id: int,
    idp_id: int,
    db: Session,
) -> identity_link_contracts.IdentityLinkRead | None:
    """Stage an update to a link's last-login timestamp."""
    row = db.execute(
        select(identity_link_models.IdentityLink).where(
            identity_link_models.IdentityLink.user_id == user_id,
            identity_link_models.IdentityLink.idp_id == idp_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    row.last_login = datetime.now(UTC)
    db.flush()
    return identity_link_serializers.to_read_schema(row)


def delete_user_identity_provider(user_id: int, idp_id: int, db: Session) -> bool:
    """Stage deletion of a user's identity-provider link."""
    matched = core_database.rowcount(
        db,
        delete(identity_link_models.IdentityLink).where(
            identity_link_models.IdentityLink.user_id == user_id,
            identity_link_models.IdentityLink.idp_id == idp_id,
        ),
    )
    db.flush()
    return bool(matched)


def select_linked_user_ids() -> Select[tuple[int]]:
    """Return a query for the ids of the users who have at least one identity-provider link.

    Returns:
        A select of user ids, for a caller to use in an ``IN`` or ``NOT IN``.
    """
    return select(identity_link_models.IdentityLink.user_id).distinct()


def get_identity_link_counts_for_users(user_ids: list[int], db: Session) -> dict[int, int]:
    """Return the number of identity-provider links for each matching user."""
    if not user_ids:
        return {}
    statement = (
        select(
            identity_link_models.IdentityLink.user_id,
            func.count(identity_link_models.IdentityLink.id).label("count"),
        )
        .where(identity_link_models.IdentityLink.user_id.in_(user_ids))
        .group_by(identity_link_models.IdentityLink.user_id)
    )
    return {user_id: count for user_id, count in db.execute(statement).all()}


def create_idp_session_token(
    session_id: str,
    user_id: int,
    idp_id: int,
    encrypted_refresh_token: str | None,
    access_token_expires_at: datetime | None,
    db: Session,
    *,
    encrypted_id_token: str | None = None,
    idp_sid: str | None = None,
) -> identity_link_contracts.IdpSessionTokenRead:
    """Stage the identity-provider sign-in behind a session, with the encrypted tokens the provider issued.

    Args:
        session_id: The session the sign-in created.
        user_id: The signed-in user.
        idp_id: The identity provider.
        encrypted_refresh_token: The encrypted refresh token, or None when none was issued.
        access_token_expires_at: When the access token expires, or None when no refresh token was issued.
        db: Database session.
        encrypted_id_token: The encrypted ID token, or None when none was issued.
        idp_sid: The provider session id of the verified ID token, or None when it named none.

    Returns:
        The staged sign-in.
    """
    row = identity_link_models.IdpSessionToken(
        session_id=session_id,
        user_id=user_id,
        idp_id=idp_id,
        refresh_token=encrypted_refresh_token,
        id_token=encrypted_id_token,
        idp_sid=idp_sid,
        access_token_expires_at=access_token_expires_at,
        refresh_token_updated_at=datetime.now(UTC) if encrypted_refresh_token is not None else None,
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    return identity_link_serializers.to_session_token_read_schema(row)


def get_idp_session_token(session_id: str, db: Session) -> identity_link_contracts.IdpSessionTokenRead | None:
    """Return the identity-provider sign-in behind a session, if it signed in through one."""
    model = identity_link_models.IdpSessionToken
    row = db.execute(select(model).where(model.session_id == session_id)).scalar_one_or_none()
    return identity_link_serializers.to_session_token_read_schema(row) if row is not None else None


def get_idp_session_token_ids_by_user_and_idp(user_id: int, idp_id: int, db: Session) -> list[str]:
    """Return the ids of the sessions the user signed in to through the provider."""
    model = identity_link_models.IdpSessionToken
    return list(db.execute(select(model.session_id).where(model.user_id == user_id, model.idp_id == idp_id)).scalars())


def get_idp_session_owners(idp_id: int, db: Session) -> list[tuple[str, int]]:
    """Return the session id and user of every sign-in through the provider."""
    model = identity_link_models.IdpSessionToken
    return [
        (row.session_id, row.user_id)
        for row in db.execute(select(model.session_id, model.user_id).where(model.idp_id == idp_id))
    ]


def get_idp_session_owners_by_sid(
    idp_id: int, idp_sid: str, db: Session, *, user_id: int | None = None
) -> list[tuple[str, int]]:
    """Return the session id and user of each sign-in through the provider that holds a provider session id.

    Args:
        idp_id: The identity provider.
        idp_sid: The provider session id.
        db: Database session.
        user_id: Restrict the result to one user's sign-ins.

    Returns:
        ``(session_id, user_id)`` per matching sign-in.
    """
    model = identity_link_models.IdpSessionToken
    stmt = select(model.session_id, model.user_id).where(model.idp_id == idp_id, model.idp_sid == idp_sid)
    if user_id is not None:
        stmt = stmt.where(model.user_id == user_id)
    return [(session_id, owner_id) for session_id, owner_id in db.execute(stmt).all()]


def get_idp_session_tokens_page(
    after_id: int, limit: int, db: Session, *, user_id: int | None = None
) -> list[identity_link_contracts.IdpSessionTokenRead]:
    """Return up to ``limit`` identity-provider sign-ins after ``after_id``, in id order, optionally one user's."""
    model = identity_link_models.IdpSessionToken
    stmt = select(model).where(model.id > after_id).order_by(model.id).limit(limit)
    if user_id is not None:
        stmt = stmt.where(model.user_id == user_id)
    return [identity_link_serializers.to_session_token_read_schema(row) for row in db.execute(stmt).scalars()]


def _lock_session_token_holding(
    session_id: str, expected_refresh_token: str | None, db: Session
) -> identity_link_models.IdpSessionToken | None:
    """Lock a session's sign-in and return it only while its refresh token is the one the caller read.

    The comparison is on what the tokens decrypt to, so a re-encryption under a new key is not a change; a
    token no configured key decrypts matches only itself.

    Args:
        session_id: The session whose sign-in to lock.
        expected_refresh_token: The encrypted refresh token the caller read, or None when it read none.
        db: Database session.

    Returns:
        The locked row, or None when it is gone or holds another token now.
    """
    model = identity_link_models.IdpSessionToken
    row = db.execute(select(model).where(model.session_id == session_id).with_for_update()).scalar_one_or_none()
    if row is None:
        return None
    if row.refresh_token == expected_refresh_token or core_cryptography.same_secret(
        row.refresh_token, expected_refresh_token
    ):
        return row
    return None


def replace_refresh_token_if_unchanged(
    session_id: str,
    expected_refresh_token: str,
    encrypted_refresh_token: str,
    access_token_expires_at: datetime,
    db: Session,
    *,
    encrypted_id_token: str | None = None,
) -> bool:
    """Stage new provider-token metadata only while the session still holds the token that was read.

    Args:
        session_id: The session whose token to replace.
        expected_refresh_token: The encrypted refresh token the caller read; compared by what it decrypts to.
        encrypted_refresh_token: The encrypted refresh token to store.
        access_token_expires_at: When the new access token expires.
        db: Database session.
        encrypted_id_token: The encrypted ID token the refresh returned; the stored one is kept when None.

    Returns:
        True when the token was replaced, False when the session holds another one now.
    """
    row = _lock_session_token_holding(session_id, expected_refresh_token, db)
    if row is None:
        return False
    row.refresh_token = encrypted_refresh_token
    if encrypted_id_token is not None:
        row.id_token = encrypted_id_token
    row.access_token_expires_at = access_token_expires_at
    row.refresh_token_updated_at = datetime.now(UTC)
    db.flush()
    return True


def clear_refresh_token_if_unchanged(session_id: str, expected_refresh_token: str, db: Session) -> bool:
    """Stage removal of provider-token metadata only while the session still holds the token that was read.

    Args:
        session_id: The session whose token to clear.
        expected_refresh_token: The encrypted refresh token the caller read; compared by what it decrypts to.
        db: Database session.

    Returns:
        True when the token was cleared, False when the session holds another one now.
    """
    row = _lock_session_token_holding(session_id, expected_refresh_token, db)
    if row is None:
        return False
    row.refresh_token = None
    row.access_token_expires_at = None
    row.refresh_token_updated_at = None
    db.flush()
    return True


def delete_idp_session_token_if_unchanged(session_id: str, expected_refresh_token: str | None, db: Session) -> bool:
    """Stage deletion of a session's sign-in only while it still holds the token that was read.

    Args:
        session_id: The session whose sign-in to delete.
        expected_refresh_token: The encrypted refresh token the caller read, or None when it read none.
        db: Database session.

    Returns:
        True when the row was deleted, False when it is gone or holds another token now.
    """
    row = _lock_session_token_holding(session_id, expected_refresh_token, db)
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def stage_reencrypt_batch_session_tokens(
    after_id: int | None, limit: int, db: Session
) -> core_key_rotation.BatchResult[int]:
    """Stage the re-encryption of up to ``limit`` session-token rows after ``after_id`` (flushed, not committed)."""
    model = identity_link_models.IdpSessionToken
    return core_key_rotation.stage_reencrypt_batch(
        model, model.id, (model.refresh_token, model.id_token), after_id, limit, db
    )
