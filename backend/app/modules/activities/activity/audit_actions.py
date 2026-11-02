"""Audit actions written by the activity package: who can see an activity or parts of it.

Ids are stable forever: rows outlive the code. ``details`` carry counts, enumerated values and changed field
names only, never a field's value.
"""

from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class VisibilityBulkUpdateDetails(VersionedPayload):
    """Details of ``activities.visibility.bulk_update``.

    Attributes:
        visibility: The visibility being applied to every activity of the user: 0 public, 1 followers, 2 private.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    visibility: int


class VisibilityUpdateDetails(VersionedPayload):
    """Details of ``activities.visibility.update``.

    Attributes:
        changed_fields: The names of the visibility and ``hide_*`` fields whose value changed.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    changed_fields: list[str]


VISIBILITY_BULK_UPDATE = jasil_audit.AuditAction(
    id="activities.visibility.bulk_update",
    category=jasil_audit.Category.AUTHORIZATION,
    severity=jasil_audit.Severity.LOW,
    description_key="audit.activities.visibility.bulk_update",
    description_default="The visibility of all of a user's activities was changed",
    details_model=VisibilityBulkUpdateDetails,
)

VISIBILITY_UPDATE = jasil_audit.AuditAction(
    id="activities.visibility.update",
    category=jasil_audit.Category.AUTHORIZATION,
    severity=jasil_audit.Severity.LOW,
    description_key="audit.activities.visibility.update",
    description_default="The visibility of an activity was changed",
    details_model=VisibilityUpdateDetails,
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (VISIBILITY_BULK_UPDATE, VISIBILITY_UPDATE)
