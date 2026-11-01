"""Audit actions written by the account-security package: credential and session changes, and step-up checks.

Ids are stable forever: rows outlive the code. ``details`` carry ids, counts and enumerated values only, never a
password, a code or a key.
"""

from enum import StrEnum
from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class StepUpMethod(StrEnum):
    """How a step-up re-authentication was attempted; ``UNSPECIFIED`` when a lockout refused it before any method."""

    PASSWORD = "password"
    MFA_CODE = "mfa_code"
    IDENTITY_PROVIDER = "identity_provider"
    UNSPECIFIED = "unspecified"


class StepUpFailureReason(StrEnum):
    """Why a step-up re-authentication was refused."""

    INVALID_CREDENTIALS = "invalid_credentials"
    LOCKED_OUT = "locked_out"


class SessionsRevokedDetails(VersionedPayload):
    """Details of an action that ends sessions.

    Attributes:
        sessions_revoked: How many sessions the action ended.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    sessions_revoked: int


class BackupCodesDetails(VersionedPayload):
    """Details of ``auth.backup_codes.generate``.

    Attributes:
        count: How many backup codes were issued.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    count: int


class ApiKeyCreateDetails(VersionedPayload):
    """Details of ``auth.api_key.create``.

    Attributes:
        scopes: The scopes the new key grants.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    scopes: list[str]


class IdentityLinkDetails(VersionedPayload):
    """Details of an identity-provider link change.

    Attributes:
        idp_id: The identity provider whose link changed.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    idp_id: int


class StepUpDetails(VersionedPayload):
    """Details of ``auth.step_up.verify``.

    Attributes:
        method: How the re-authentication was attempted.
        reason: Why it was refused; None on success.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    method: StepUpMethod
    reason: StepUpFailureReason | None = None


PASSWORD_CHANGE = jasil_audit.AuditAction(
    id="auth.password.change",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.password.change",
    description_default="A user changed their password",
    details_model=SessionsRevokedDetails,
)

PASSWORD_SET = jasil_audit.AuditAction(
    id="auth.password.set",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.password.set",
    description_default="An administrator set a user's password",
    details_model=SessionsRevokedDetails,
)

MFA_ENABLE = jasil_audit.AuditAction(
    id="auth.mfa.enable",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.mfa.enable",
    description_default="Two-factor authentication was turned on",
)

MFA_DISABLE = jasil_audit.AuditAction(
    id="auth.mfa.disable",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.mfa.disable",
    description_default="Two-factor authentication was turned off",
)

BACKUP_CODES_GENERATE = jasil_audit.AuditAction(
    id="auth.backup_codes.generate",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.auth.backup_codes.generate",
    description_default="New two-factor backup codes were issued",
    details_model=BackupCodesDetails,
)

API_KEY_CREATE = jasil_audit.AuditAction(
    id="auth.api_key.create",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.api_key.create",
    description_default="An API key was created",
    details_model=ApiKeyCreateDetails,
)

API_KEY_REVOKE = jasil_audit.AuditAction(
    id="auth.api_key.revoke",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.auth.api_key.revoke",
    description_default="An API key was revoked",
)

API_KEY_DELETE = jasil_audit.AuditAction(
    id="auth.api_key.delete",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.auth.api_key.delete",
    description_default="An API key was deleted",
)

SESSION_REVOKE = jasil_audit.AuditAction(
    id="auth.session.revoke",
    category=jasil_audit.Category.IDENTITY,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.auth.session.revoke",
    description_default="Sessions were signed out",
    details_model=SessionsRevokedDetails,
)

IDENTITY_LINK_UNLINK = jasil_audit.AuditAction(
    id="auth.identity_link.unlink",
    category=jasil_audit.Category.IDENTITY,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.identity_link.unlink",
    description_default="A sign-in provider was unlinked from an account",
    details_model=IdentityLinkDetails,
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
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (
    PASSWORD_CHANGE,
    PASSWORD_SET,
    MFA_ENABLE,
    MFA_DISABLE,
    BACKUP_CODES_GENERATE,
    API_KEY_CREATE,
    API_KEY_REVOKE,
    API_KEY_DELETE,
    SESSION_REVOKE,
    IDENTITY_LINK_UNLINK,
    STEP_UP_VERIFY,
)
