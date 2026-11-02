"""Audit actions written by the users package: accounts an administrator creates, changes, approves or deletes.

Ids are stable forever: rows outlive the code. ``details`` carry enumerated values and changed field names
only, never a field's value.
"""

from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class UserCreateDetails(VersionedPayload):
    """Details of ``users.user.create``.

    Attributes:
        access_type: The access tier the account was created with.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    access_type: str


class UserUpdateDetails(VersionedPayload):
    """Details of ``users.user.update``.

    Attributes:
        changed_fields: The names of the fields whose value changed.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    changed_fields: list[str]


USER_CREATE = jasil_audit.AuditAction(
    id="users.user.create",
    category=jasil_audit.Category.ADMIN,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.users.user.create",
    description_default="An account was created",
    details_model=UserCreateDetails,
)

USER_UPDATE = jasil_audit.AuditAction(
    id="users.user.update",
    category=jasil_audit.Category.ADMIN,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.users.user.update",
    description_default="An administrator changed an account",
    details_model=UserUpdateDetails,
)

USER_APPROVE = jasil_audit.AuditAction(
    id="users.user.approve",
    category=jasil_audit.Category.ADMIN,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.users.user.approve",
    description_default="An administrator approved a sign-up",
)

USER_DELETE = jasil_audit.AuditAction(
    id="users.user.delete",
    category=jasil_audit.Category.ADMIN,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.users.user.delete",
    description_default="An account was deleted",
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (USER_CREATE, USER_UPDATE, USER_APPROVE, USER_DELETE)
