"""Audit actions written by the Garmin package: the account link, unlink and revocation.

Ids are stable forever: rows outlive the code. ``details`` carry enumerated values only, never a username, a
password, an MFA code or a token.
"""

from enum import StrEnum
from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class LinkFailureReason(StrEnum):
    """Why Garmin Connect refused to link an account.

    Attributes:
        INVALID_CREDENTIALS: The username or password was refused.
        INCORRECT_MFA: The multi-factor code was refused or did not arrive in time.
        TOO_MANY_REQUESTS: Garmin Connect is rate limiting the login.
    """

    INVALID_CREDENTIALS = "invalid_credentials"
    INCORRECT_MFA = "incorrect_mfa"
    TOO_MANY_REQUESTS = "too_many_requests"


class LinkFailureDetails(VersionedPayload):
    """Details of ``garmin.account.link``.

    Attributes:
        reason: Why Garmin Connect refused the link; None on success.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    reason: LinkFailureReason | None = None


ACCOUNT_LINK = jasil_audit.AuditAction(
    id="garmin.account.link",
    category=jasil_audit.Category.INTEGRATION,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.garmin.account.link",
    description_default="A Garmin Connect account was linked",
    details_model=LinkFailureDetails,
)

ACCOUNT_UNLINK = jasil_audit.AuditAction(
    id="garmin.account.unlink",
    category=jasil_audit.Category.INTEGRATION,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.garmin.account.unlink",
    description_default="A Garmin Connect account was unlinked",
)

ACCOUNT_REVOKE = jasil_audit.AuditAction(
    id="garmin.account.revoke",
    category=jasil_audit.Category.INTEGRATION,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.garmin.account.revoke",
    description_default="A Garmin Connect account was unlinked because Garmin Connect rejected its token",
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (ACCOUNT_LINK, ACCOUNT_UNLINK, ACCOUNT_REVOKE)
