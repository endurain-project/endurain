"""Audit actions written by the login_audit package: sign-ins and the sign-ins that were refused.

Ids are stable forever: rows outlive the code. ``details`` carry ids and enumerated reasons only, never a
username that was not matched, a token, an OAuth state, a provider subject or a password.
"""

from enum import StrEnum
from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class LoginMethod(StrEnum):
    """How a sign-in was attempted."""

    PASSWORD = "password"
    IDENTITY_PROVIDER = "identity_provider"


class LoginFailureReason(StrEnum):
    """Why a sign-in was refused."""

    INVALID_CREDENTIALS = "invalid_credentials"
    LOCKED_OUT = "locked_out"
    INACTIVE = "inactive"
    PASSWORD_SIGN_IN_DISABLED = "password_sign_in_disabled"
    INVALID_MFA_CODE = "invalid_mfa_code"
    MFA_CHALLENGE_EXPIRED = "mfa_challenge_expired"
    MFA_CHALLENGE_CLAIMED = "mfa_challenge_claimed"
    INVALID_STATE = "invalid_state"
    INVALID_ID_TOKEN = "invalid_id_token"
    PROVISIONING_REFUSED = "provisioning_refused"
    PKCE_MISMATCH = "pkce_mismatch"
    EXCHANGE_REPLAYED = "exchange_replayed"


class LoginDetails(VersionedPayload):
    """Details of ``auth.session.login``.

    Attributes:
        method: How the sign-in was attempted.
        mfa: Whether a second factor was verified (or, on a failure, was the step refused).
        reason: Why the sign-in was refused; None on success.
        new_device: Whether the sign-in was announced as one from a new device; False on a refusal.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 3

    method: LoginMethod
    mfa: bool = False
    reason: LoginFailureReason | None = None
    new_device: bool = False


LOGIN = jasil_audit.AuditAction(
    id="auth.session.login",
    category=jasil_audit.Category.AUTHENTICATION,
    severity=jasil_audit.Severity.LOW,
    description_key="audit.auth.session.login",
    description_default="A sign-in was attempted",
    details_model=LoginDetails,
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (LOGIN,)
