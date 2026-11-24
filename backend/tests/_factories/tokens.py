"""One-time tokens and second factors, staged through the modules' own create paths, for tests on the real database."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jasil.audit as jasil_audit
import jasil.testing as jasil_testing
import pyotp
import sqlalchemy as sa
from jasil.audit.models import AuditLog
from jasil.backends.state_memory import MemoryState
from sqlalchemy.orm import Session, sessionmaker

import modules.auth.computation as token_hashing
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.mfa.service as mfa_service
import modules.auth.mfa.totp_replay_store as mfa_totp_replay_store
import modules.auth.password_reset_tokens.models as password_reset_models
import modules.auth.password_reset_tokens.service as password_reset_service
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.users.users.schema as users_schema


def audit_rows(sessions: sessionmaker[Session], action: jasil_audit.AuditAction) -> list[AuditLog]:
    """Read the audit rows of an action back in a new session, oldest first.

    Args:
        sessions: The application's session factory (``committed_sessions``).
        action: The action to list.

    Returns:
        The committed rows of the action.
    """
    with sessions() as db:
        return list(
            db.scalars(sa.select(AuditLog).where(AuditLog.action_id == action.id).order_by(AuditLog.occurred_at))
        )


def make_reset_token(db: Session, user: users_schema.UserRead, *, expires_at: datetime | None = None) -> str:
    """Stage a password-reset token for a user the way a reset request does, replacing their unused ones.

    Args:
        db: Database session; the token is flushed, not committed.
        user: The token's owner.
        expires_at: When the token expires; the request's one hour from now when omitted.

    Returns:
        The raw token, which is not stored.
    """
    token, token_hash = token_hashing.generate_token_and_hash()
    password_reset_service._stage_password_reset_token(user.id, token_hash, db)
    if expires_at is not None:
        db.execute(
            sa.update(password_reset_models.PasswordResetToken)
            .where(password_reset_models.PasswordResetToken.token_hash == token_hash)
            .values(expires_at=expires_at)
        )
        db.flush()
    return token


def make_sign_up_token(db: Session, user: users_schema.UserRead, *, expires_at: datetime | None = None) -> str:
    """Stage the verification token of a sign-up for the user's address, replacing their unused ones.

    Args:
        db: Database session; the token is flushed, not committed.
        user: The account the token verifies.
        expires_at: When the token expires; its 24 hours from now when omitted.

    Returns:
        The raw token, which is not stored.
    """
    token, token_hash = token_hashing.generate_token_and_hash()
    sign_up_service._stage_sign_up_token(user.id, user.email, None, db, token=token)
    if expires_at is not None:
        db.execute(
            sa.update(sign_up_models.SignUpToken)
            .where(sign_up_models.SignUpToken.token_hash == token_hash)
            .values(expires_at=expires_at)
        )
        db.flush()
    return token


@dataclass(frozen=True)
class EmailChange:
    """A requested email change.

    Attributes:
        token: The raw token of the confirmation link mailed to the new address.
        revert_token: The token of the "this wasn't me" link mailed to the previous address.
        change_id: The change the revert link names.
    """

    token: str
    revert_token: str
    change_id: uuid.UUID


def make_email_change(
    db: Session,
    user: users_schema.UserRead,
    new_email: str,
    *,
    expires_at: datetime | None = None,
    revert_window: timedelta = sign_up_service.EMAIL_CHANGE_REVERT_WINDOW,
) -> EmailChange:
    """Stage an email change of the user's own, under the account's current security generation.

    Args:
        db: Database session; the token is flushed, not committed.
        user: The account whose address changes.
        new_email: The pending address.
        expires_at: When the confirmation token expires; its 24 hours from now when omitted.
        revert_window: How long from now the "this wasn't me" link works; negative for a window already closed.

    Returns:
        The confirmation token and the revert link's token.
    """
    token, token_hash = token_hashing.generate_token_and_hash()
    change_id = uuid.uuid4()
    revert_until = datetime.now(UTC) + revert_window
    sign_up_service._stage_sign_up_token(
        user.id,
        new_email,
        user.email,
        db,
        token=token,
        security_generation=security_generation_integration.current_generation(user.id, db),
        change_id=change_id,
        revert_until=revert_until,
    )
    if expires_at is not None:
        db.execute(
            sa.update(sign_up_models.SignUpToken)
            .where(sign_up_models.SignUpToken.token_hash == token_hash)
            .values(expires_at=expires_at)
        )
        db.flush()
    return EmailChange(
        token=token,
        revert_token=f"{change_id}.{sign_up_service._revert_mac(change_id, revert_until)}",
        change_id=change_id,
    )


@dataclass(frozen=True)
class MfaFactors:
    """A user's enrolled second factors.

    Attributes:
        secret: The TOTP secret, shown once at enrolment.
        backup_codes: The unused backup codes, shown once at enrolment.
    """

    secret: str
    backup_codes: list[str]


class _EnrolmentReplayGuard:
    """Records the TOTP step the enrolment code used, in a state of its own so the platform's replay store is clean."""

    def __init__(self) -> None:
        self._state = MemoryState(jasil_testing.FixedClock())

    def claim_totp_step(self, user_id: uuid.UUID, step: int) -> bool:
        return mfa_totp_replay_store.claim_totp_step(self._state, user_id, step)


def make_mfa(db: Session, user: users_schema.UserRead) -> MfaFactors:
    """Enrol a user in TOTP MFA through the enrolment path, with its ten backup codes.

    Args:
        db: Database session; the factors are flushed, not committed.
        user: The user to enrol.

    Returns:
        The TOTP secret and the backup codes.
    """
    secret = pyotp.random_base32()
    backup_codes = mfa_service.enable_user_mfa(
        user.id,
        secret,
        pyotp.TOTP(secret).now(),
        credentials_integration.get_password_hasher(),
        db,
        replay_guard=_EnrolmentReplayGuard(),
    )
    db.flush()
    return MfaFactors(secret=secret, backup_codes=backup_codes)


def totp_code(secret: str, *, steps_ahead: int = 0) -> str:
    """Return the TOTP code of the current 30-second step, or of one a number of steps ahead.

    A code one step ahead is accepted too, for clock drift, and has not been used by an enrolment.

    Args:
        secret: The TOTP secret.
        steps_ahead: How many steps after the current one.
    """
    totp = pyotp.TOTP(secret)
    return totp.generate_otp(totp.timecode(datetime.now(UTC)) + steps_ahead)
