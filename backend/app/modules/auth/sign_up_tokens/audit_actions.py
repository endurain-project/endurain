"""Audit actions written by the sign-up-tokens package.

Ids are stable forever: rows outlive the code. ``details`` carry flags only, never a password or a token.
"""

from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class SignUpConfirmDetails(VersionedPayload):
    """Details of ``auth.sign_up.confirm``.

    Attributes:
        password_set: Whether the confirmation set the account's password; None for a refused token.
        reason: Why a token was refused, when it is known: ``security_changed`` for an email change requested before
            a security change of the account.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    password_set: bool | None = None
    reason: str | None = None


SIGN_UP_CONFIRM = jasil_audit.AuditAction(
    id="auth.sign_up.confirm",
    category=jasil_audit.Category.IDENTITY,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.sign_up.confirm",
    description_default="An email address was confirmed with an emailed link",
    details_model=SignUpConfirmDetails,
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (SIGN_UP_CONFIRM,)
