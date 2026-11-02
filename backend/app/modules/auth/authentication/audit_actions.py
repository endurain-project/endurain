"""Audit actions written by the authentication package: sign-in, sign-out and refused credentials.

Ids are stable forever: rows outlive the code. ``details`` carry ids and enumerated reasons only, never a
username that was not matched, a token or a password.
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


class LoginDetails(VersionedPayload):
    """Details of ``auth.session.login``.

    Attributes:
        method: How the sign-in was attempted.
        mfa: Whether a second factor was verified (or, on a failure, was the step refused).
        reason: Why the sign-in was refused; None on success.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    method: LoginMethod
    mfa: bool = False
    reason: LoginFailureReason | None = None


class ScopeDeniedDetails(VersionedPayload):
    """Details of ``auth.scope.denied``.

    Attributes:
        missing_scopes: The scopes the route required and the credential did not grant.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    missing_scopes: list[str]


LOGIN = jasil_audit.AuditAction(
    id="auth.session.login",
    category=jasil_audit.Category.AUTHENTICATION,
    severity=jasil_audit.Severity.LOW,
    description_key="audit.auth.session.login",
    description_default="A sign-in was attempted",
    details_model=LoginDetails,
)

LOGOUT = jasil_audit.AuditAction(
    id="auth.session.logout",
    category=jasil_audit.Category.AUTHENTICATION,
    severity=jasil_audit.Severity.INFO,
    description_key="audit.auth.session.logout",
    description_default="A user signed out",
)

REFRESH_TOKEN_REUSE = jasil_audit.AuditAction(
    id="auth.session.refresh_reuse",
    category=jasil_audit.Category.AUTHENTICATION,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.session.refresh_reuse",
    description_default="A used refresh token was replayed and its session was revoked",
)

SCOPE_DENIED = jasil_audit.AuditAction(
    id="auth.scope.denied",
    category=jasil_audit.Category.AUTHORIZATION,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.auth.scope.denied",
    description_default="A request lacked a required permission",
    details_model=ScopeDeniedDetails,
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (LOGIN, LOGOUT, REFRESH_TOKEN_REUSE, SCOPE_DENIED)
