"""Audit actions written by the identity-providers package.

Ids are stable forever: rows outlive the code. ``details`` carry ids only, never a provider token or subject.
"""

from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class IdentityLinkDetails(VersionedPayload):
    """Details of ``auth.identity_link.link``.

    Attributes:
        idp_id: The identity provider that was linked.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    idp_id: int


IDENTITY_LINK_LINK = jasil_audit.AuditAction(
    id="auth.identity_link.link",
    category=jasil_audit.Category.IDENTITY,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.auth.identity_link.link",
    description_default="A sign-in provider was linked to an account",
    details_model=IdentityLinkDetails,
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (IDENTITY_LINK_LINK,)
