"""Audit actions written by the login_audit package: sign-ins, the sign-ins that were refused and step-ups.

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
    MFA_CHALLENGE_NETWORK_MISMATCH = "mfa_challenge_network_mismatch"
    MFA_CHALLENGE_CLAIMED = "mfa_challenge_claimed"
    PASSWORD_CHANGE_CHALLENGE_INVALID = "password_change_challenge_invalid"
    PASSWORD_CHANGE_CHALLENGE_CLAIMED = "password_change_challenge_claimed"
    INVALID_STATE = "invalid_state"
    INVALID_ID_TOKEN = "invalid_id_token"
    PROVISIONING_REFUSED = "provisioning_refused"
    PKCE_MISMATCH = "pkce_mismatch"
    EXCHANGE_REPLAYED = "exchange_replayed"
    TOKEN_EXCHANGE_FAILED = "token_exchange_failed"
    NO_SUBJECT = "no_subject"
    PROVIDER_ERROR = "provider_error"


class StepUpMethod(StrEnum):
    """How a step-up re-authentication was attempted; ``UNSPECIFIED`` when a lockout refused it before any method."""

    PASSWORD = "password"
    MFA_CODE = "mfa_code"
    IDENTITY_PROVIDER = "identity_provider"
    UNSPECIFIED = "unspecified"


class StepUpFailureReason(StrEnum):
    """Why a step-up re-authentication was refused.

    Attributes:
        INVALID_CREDENTIALS: The password or second factor was wrong.
        LOCKED_OUT: Too many failed attempts locked the step-up.
        NOT_LINKED: The provider signed in an account that is not linked to the user.
        NOT_FRESH: The provider's ID token did not prove a recent enough sign-in.
        PROVIDER_FAILURE: The provider failed, refused the code, sent no usable ID token or subject, or the
            callback failed unexpectedly.
        BROWSER_MISMATCH: The callback came from a browser other than the one that started the step-up.
        INVALID_STATE: The step-up's OAuth state was unknown, bound to another provider or already used.
    """

    INVALID_CREDENTIALS = "invalid_credentials"
    LOCKED_OUT = "locked_out"
    NOT_LINKED = "not_linked"
    NOT_FRESH = "not_fresh"
    PROVIDER_FAILURE = "provider_failure"
    BROWSER_MISMATCH = "browser_mismatch"
    INVALID_STATE = "invalid_state"


class LoginDetails(VersionedPayload):
    """Details of ``auth.session.login``.

    Attributes:
        method: How the sign-in was attempted.
        mfa: Whether a second factor was verified (or, on a failure, was the step refused).
        reason: Why the sign-in was refused; None on success.
        new_device: Whether the sign-in was announced as one from a new device; False on a refusal.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 5

    method: LoginMethod
    mfa: bool = False
    reason: LoginFailureReason | None = None
    new_device: bool = False


class StepUpDetails(VersionedPayload):
    """Details of ``auth.step_up.verify``.

    Attributes:
        method: How the re-authentication was attempted.
        reason: Why it was refused; None on success.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 2

    method: StepUpMethod
    reason: StepUpFailureReason | None = None


LOGIN = jasil_audit.AuditAction(
    id="auth.session.login",
    category=jasil_audit.Category.AUTHENTICATION,
    severity=jasil_audit.Severity.LOW,
    description_key="audit.auth.session.login",
    description_default="A sign-in was attempted",
    details_model=LoginDetails,
)

STEP_UP_VERIFY = jasil_audit.AuditAction(
    id="auth.step_up.verify",
    category=jasil_audit.Category.AUTHENTICATION,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.auth.step_up.verify",
    description_default="A sensitive action asked the user to confirm who they are",
    details_model=StepUpDetails,
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (LOGIN, STEP_UP_VERIFY)
