"""Audit actions written by the sessions package and the packages that end sessions through it.

Ids are stable forever: rows outlive the code. ``details`` carry counts only, never a session token.
"""

from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class SessionsRevokedDetails(VersionedPayload):
    """Details of an action that ends sessions.

    Attributes:
        sessions_revoked: How many sessions the action ended.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    sessions_revoked: int


SESSION_REVOKE = jasil_audit.AuditAction(
    id="auth.session.revoke",
    category=jasil_audit.Category.IDENTITY,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.auth.session.revoke",
    description_default="Sessions were signed out",
    details_model=SessionsRevokedDetails,
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (SESSION_REVOKE,)
