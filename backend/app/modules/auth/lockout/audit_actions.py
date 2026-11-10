"""Audit actions written by the lockout package.

Ids are stable forever: rows outlive the code. ``details`` carry the counter and its failure count only, never the
username the counter is keyed on.
"""

from enum import StrEnum
from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class LockoutCounter(StrEnum):
    """Which failure counter closed the gate."""

    LOGIN = "login"
    LOGIN_ACCOUNT = "login_account"
    MFA = "mfa"
    MFA_ACCOUNT = "mfa_account"
    STEP_UP = "step_up"


class LockoutApplyDetails(VersionedPayload):
    """Details of ``auth.lockout.apply``.

    Attributes:
        counter: The failure counter that locked.
        failed_attempts: The count of failed attempts that applied the lockout.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 3

    counter: LockoutCounter
    failed_attempts: int


LOCKOUT_APPLY = jasil_audit.AuditAction(
    id="auth.lockout.apply",
    category=jasil_audit.Category.AUTHENTICATION,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.lockout.apply",
    description_default="A sign-in lockout was applied after repeated failures",
    details_model=LockoutApplyDetails,
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (LOCKOUT_APPLY,)
