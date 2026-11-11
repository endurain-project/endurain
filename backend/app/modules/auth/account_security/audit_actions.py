"""Audit actions written by the account-security package: credential and session changes.

Ids are stable forever: rows outlive the code. ``details`` carry ids, counts and enumerated values only, never a
password, a code or a key.
"""

from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

import modules.auth.sessions.audit_actions as sessions_audit_actions


class BackupCodesDetails(VersionedPayload):
    """Details of ``auth.backup_codes.generate``.

    Attributes:
        count: How many backup codes were issued.
        sessions_revoked: How many of the user's other sessions the change ended.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    count: int
    sessions_revoked: int = 0


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


PASSWORD_CHANGE = jasil_audit.AuditAction(
    id="auth.password.change",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.password.change",
    description_default="A user changed their password",
    details_model=sessions_audit_actions.SessionsRevokedDetails,
)

PASSWORD_SET = jasil_audit.AuditAction(
    id="auth.password.set",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.password.set",
    description_default="An administrator set a user's password",
    details_model=sessions_audit_actions.SessionsRevokedDetails,
)

MFA_ENABLE = jasil_audit.AuditAction(
    id="auth.mfa.enable",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.mfa.enable",
    description_default="Two-factor authentication was turned on",
    details_model=sessions_audit_actions.SessionsRevokedDetails,
)

MFA_DISABLE = jasil_audit.AuditAction(
    id="auth.mfa.disable",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.mfa.disable",
    description_default="Two-factor authentication was turned off",
    details_model=sessions_audit_actions.SessionsRevokedDetails,
)

MFA_RESET = jasil_audit.AuditAction(
    id="auth.mfa.reset",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.mfa.reset",
    description_default="An administrator reset a user's two-factor authentication",
    details_model=sessions_audit_actions.SessionsRevokedDetails,
)

PASSWORD_CHANGE_REQUIRE = jasil_audit.AuditAction(
    id="auth.password.require_change",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.password.require_change",
    description_default="An administrator required a user to change their password",
    details_model=sessions_audit_actions.SessionsRevokedDetails,
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

IDENTITY_LINK_UNLINK = jasil_audit.AuditAction(
    id="auth.identity_link.unlink",
    category=jasil_audit.Category.IDENTITY,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.identity_link.unlink",
    description_default="A sign-in provider was unlinked from an account",
    details_model=IdentityLinkDetails,
)

DEVICE_FORGET = jasil_audit.AuditAction(
    id="auth.device.forget",
    category=jasil_audit.Category.IDENTITY,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.auth.device.forget",
    description_default="A known sign-in device was forgotten",
)

STEP_UP_SESSION_END = jasil_audit.AuditAction(
    id="auth.session.step_up_end",
    category=jasil_audit.Category.AUTHENTICATION,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.session.step_up_end",
    description_default="A session was ended after repeated failed step-up attempts",
    details_model=sessions_audit_actions.SessionsRevokedDetails,
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (
    PASSWORD_CHANGE,
    PASSWORD_SET,
    MFA_ENABLE,
    MFA_DISABLE,
    MFA_RESET,
    PASSWORD_CHANGE_REQUIRE,
    BACKUP_CODES_GENERATE,
    API_KEY_CREATE,
    API_KEY_REVOKE,
    API_KEY_DELETE,
    IDENTITY_LINK_UNLINK,
    DEVICE_FORGET,
    STEP_UP_SESSION_END,
)
