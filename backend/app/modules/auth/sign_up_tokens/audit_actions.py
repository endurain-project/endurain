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
        reason: Why a token was refused, when it is known: ``sign_up_disabled`` for a sign-up confirmed while
            sign-up is off, ``security_changed`` for an email change requested before a security change of the account.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 2

    password_set: bool | None = None
    reason: str | None = None


class EmailChangeCancelDetails(VersionedPayload):
    """Details of ``auth.email_change.cancel``.

    Attributes:
        sessions_revoked: How many of the user's sessions the cancellation ended.
        api_keys_revoked: How many of the user's API keys it revoked.
        change_applied: Whether the change, or a later change reverted by the link, had been confirmed.
        email_restored: Whether the account's previous address was put back.
        reset_tokens_revoked: Whether the account's unused password-reset tokens were revoked; every accepted link
            revokes them, through the restored address or directly.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 3

    sessions_revoked: int = 0
    api_keys_revoked: int = 0
    change_applied: bool = False
    email_restored: bool = False
    reset_tokens_revoked: bool = False


SIGN_UP_CONFIRM = jasil_audit.AuditAction(
    id="auth.sign_up.confirm",
    category=jasil_audit.Category.IDENTITY,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.sign_up.confirm",
    description_default="An email address was confirmed with an emailed link",
    details_model=SignUpConfirmDetails,
)

EMAIL_CHANGE_CANCEL = jasil_audit.AuditAction(
    id="auth.email_change.cancel",
    category=jasil_audit.Category.IDENTITY,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.email_change.cancel",
    description_default="A requested email change was reported as not made by the account's owner",
    details_model=EmailChangeCancelDetails,
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (SIGN_UP_CONFIRM, EMAIL_CHANGE_CANCEL)
