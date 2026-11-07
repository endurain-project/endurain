"""Persistence operations for local credentials."""

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.credentials.models as credentials_models
import modules.auth.credentials.serializers as credentials_serializers


def get_credential(user_id: int, db: Session) -> credentials_contracts.CredentialRead | None:
    """Return the user's stored local credential, if any."""
    row = db.execute(
        select(credentials_models.LocalCredential).where(credentials_models.LocalCredential.user_id == user_id)
    ).scalar_one_or_none()
    return credentials_serializers.to_read_schema(row) if row is not None else None


def upsert_password_hash(user_id: int, password_hash: str, change_required: bool, db: Session) -> None:
    """Stage a local password hash insert or update, with whether its owner must replace the password."""
    row = db.execute(
        select(credentials_models.LocalCredential).where(credentials_models.LocalCredential.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        db.add(
            credentials_models.LocalCredential(
                user_id=user_id, password_hash=password_hash, password_change_required=change_required
            )
        )
    else:
        row.password_hash = password_hash
        row.password_change_required = change_required
    db.flush()


def set_password_change_required(user_id: int, db: Session) -> None:
    """Stage the requirement that a user replace their password at the next sign-in, leaving the hash as it is."""
    db.execute(
        update(credentials_models.LocalCredential)
        .where(credentials_models.LocalCredential.user_id == user_id)
        .values(password_change_required=True)
    )
    db.flush()


def delete_credential(user_id: int, db: Session) -> None:
    """Stage deletion of a user's local credential."""
    db.execute(delete(credentials_models.LocalCredential).where(credentials_models.LocalCredential.user_id == user_id))
    db.flush()
