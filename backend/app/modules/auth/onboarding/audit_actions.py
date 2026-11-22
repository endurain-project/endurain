"""Audit actions written by the onboarding package.

Ids are stable forever: rows outlive the code. ``details`` carry an enumerated reason only, never a setup token or a
password.
"""

from enum import StrEnum
from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class OnboardingRefusalReason(StrEnum):
    """Why a first-run onboarding attempt was refused."""

    ACCOUNT_EXISTS = "account_exists"
    INVALID_TOKEN = "invalid_token"
    PASSWORD_POLICY = "password_policy"


class OnboardingRefusalDetails(VersionedPayload):
    """Details of ``auth.onboarding.refuse``.

    Attributes:
        reason: Why the attempt was refused.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    reason: OnboardingRefusalReason


ONBOARDING_REFUSE = jasil_audit.AuditAction(
    id="auth.onboarding.refuse",
    category=jasil_audit.Category.IDENTITY,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.auth.onboarding.refuse",
    description_default="A first-run onboarding attempt was refused",
    details_model=OnboardingRefusalDetails,
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (ONBOARDING_REFUSE,)
