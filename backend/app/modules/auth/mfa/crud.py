"""Stage-only persistence operations for MFA state."""

from sqlalchemy import select
from sqlalchemy.orm import Session

import modules.auth.mfa.contracts as mfa_contracts
import modules.auth.mfa.models as auth_mfa_models
import modules.auth.mfa.serializers as mfa_serializers


def get_user_mfa_row(user_id: int, db: Session) -> mfa_contracts.MFAStateRead | None:
    """Return the MFA state for a user."""
    stmt = select(auth_mfa_models.UsersMFA).where(auth_mfa_models.UsersMFA.user_id == user_id)
    row = db.execute(stmt).scalar_one_or_none()
    return mfa_serializers.to_read_schema(row) if row is not None else None


def get_mfa_enabled_for_users(user_ids: list[int], db: Session) -> dict[int, bool]:
    """Return enabled MFA state for the supplied users in one query."""
    if not user_ids:
        return {}
    stmt = select(auth_mfa_models.UsersMFA.user_id).where(
        auth_mfa_models.UsersMFA.user_id.in_(user_ids),
        auth_mfa_models.UsersMFA.mfa_enabled.is_(True),
        auth_mfa_models.UsersMFA.mfa_secret.is_not(None),
    )
    return {row.user_id: True for row in db.execute(stmt).all()}


def update_user_mfa(user_id: int, db: Session, *, encrypted_secret: str | None = None) -> None:
    """Stage an MFA update, creating the companion row when needed."""
    mfa_enabled = bool(encrypted_secret)
    stmt = select(auth_mfa_models.UsersMFA).where(auth_mfa_models.UsersMFA.user_id == user_id)
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        row = auth_mfa_models.UsersMFA(user_id=user_id, mfa_enabled=mfa_enabled, mfa_secret=encrypted_secret)
        db.add(row)
    else:
        row.mfa_enabled = mfa_enabled
        row.mfa_secret = encrypted_secret
    db.flush()


def create_users_mfa_row(user_id: int, db: Session) -> mfa_contracts.MFAStateRead:
    """Stage the default disabled MFA row for a newly created user."""
    row = auth_mfa_models.UsersMFA(user_id=user_id, mfa_enabled=False, mfa_secret=None)
    db.add(row)
    db.flush()
    db.refresh(row)
    return mfa_serializers.to_read_schema(row)
