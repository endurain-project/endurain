"""Stage-only persistence operations for MFA factors."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

import core.key_rotation as core_key_rotation
import modules.auth.constants as auth_constants
import modules.auth.mfa.contracts as mfa_contracts
import modules.auth.mfa.models as auth_mfa_models
import modules.auth.mfa.serializers as mfa_serializers


def get_totp_factor(user_id: uuid.UUID, db: Session) -> mfa_contracts.MFAFactorRead | None:
    """Return a user's TOTP factor."""
    stmt = select(auth_mfa_models.MFAFactor).where(
        auth_mfa_models.MFAFactor.user_id == user_id,
        auth_mfa_models.MFAFactor.type == auth_constants.MFAFactorType.TOTP,
    )
    row = db.execute(stmt).scalar_one_or_none()
    return mfa_serializers.to_read_schema(row) if row is not None else None


def get_mfa_enabled_for_users(user_ids: list[uuid.UUID], db: Session) -> dict[uuid.UUID, bool]:
    """Return which of the supplied users have a second factor, in one query."""
    if not user_ids:
        return {}
    stmt = select(auth_mfa_models.MFAFactor.user_id).where(auth_mfa_models.MFAFactor.user_id.in_(user_ids)).distinct()
    return {row.user_id: True for row in db.execute(stmt).all()}


def set_totp_factor(user_id: uuid.UUID, encrypted_secret: str, db: Session) -> None:
    """Stage a user's TOTP factor, replacing the one they have."""
    delete_user_factors(user_id, db)
    db.add(
        auth_mfa_models.MFAFactor(
            user_id=user_id, type=auth_constants.MFAFactorType.TOTP.value, credential=encrypted_secret
        )
    )
    db.flush()


def delete_user_factors(user_id: uuid.UUID, db: Session) -> None:
    """Stage removal of every second factor a user has."""
    db.execute(delete(auth_mfa_models.MFAFactor).where(auth_mfa_models.MFAFactor.user_id == user_id))


def mark_factor_used(factor_id: uuid.UUID, db: Session) -> None:
    """Stage the time a factor verified a sign-in or step-up."""
    db.execute(
        update(auth_mfa_models.MFAFactor)
        .where(auth_mfa_models.MFAFactor.id == factor_id)
        .values(last_used_at=datetime.now(UTC))
    )


def stage_reencrypt_batch_mfa(
    after_id: uuid.UUID | None, limit: int, db: Session
) -> core_key_rotation.BatchResult[uuid.UUID]:
    """Stage the re-encryption of up to ``limit`` factor rows after ``after_id`` (flushed, not committed)."""
    model = auth_mfa_models.MFAFactor
    return core_key_rotation.stage_reencrypt_batch(model, model.id, (model.credential,), after_id, limit, db)
