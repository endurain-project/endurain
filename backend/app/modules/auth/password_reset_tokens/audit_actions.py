"""Audit actions written by the password-reset package.

Ids are stable forever: rows outlive the code. A reset row's ``details`` carry one flag; the row's target names
the user, and a reset token or the address it was requested for never reaches the trail.
"""

from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class PasswordResetDetails(VersionedPayload):
    """Details of ``auth.password.reset``.

    Attributes:
        unverified_account_cleaned: Whether the account's email had never been verified, so the reset removed its
            identity-provider links and second factors and marked the email verified.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    unverified_account_cleaned: bool = False


PASSWORD_RESET = jasil_audit.AuditAction(
    id="auth.password.reset",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.password.reset",
    description_default="A password was reset with an emailed link",
    details_model=PasswordResetDetails,
)

PASSWORD_RESET_REQUEST = jasil_audit.AuditAction(
    id="auth.password_reset.request",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.LOW,
    description_key="audit.auth.password_reset.request",
    description_default="A password reset link was requested",
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (PASSWORD_RESET, PASSWORD_RESET_REQUEST)
