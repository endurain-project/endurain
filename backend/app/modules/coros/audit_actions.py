"""Audit actions written by the COROS package: the account link and unlink.

Ids are stable forever: rows outlive the code. ``details`` carry enumerated values only, never a token, a code or a
secret.
"""

from enum import StrEnum
from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class LinkFailureReason(StrEnum):
    """Why COROS refused to finish an account link.

    Attributes:
        INVALID_STATE: The OAuth state was unknown, expired or belonged to another user.
        UPSTREAM: COROS refused the authorization code or could not be reached.
    """

    INVALID_STATE = "invalid_state"
    UPSTREAM = "upstream"


class LinkFailureDetails(VersionedPayload):
    """Details of ``coros.account.link`` when the link failed.

    Attributes:
        reason: Why the link failed; None on success.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    reason: LinkFailureReason | None = None


ACCOUNT_LINK = jasil_audit.AuditAction(
    id="coros.account.link",
    category=jasil_audit.Category.INTEGRATION,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.coros.account.link",
    description_default="A COROS account was linked",
    details_model=LinkFailureDetails,
)

ACCOUNT_UNLINK = jasil_audit.AuditAction(
    id="coros.account.unlink",
    category=jasil_audit.Category.INTEGRATION,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.coros.account.unlink",
    description_default="A COROS account was unlinked",
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (ACCOUNT_LINK, ACCOUNT_UNLINK)
