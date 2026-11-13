"""Audit actions written by the users package: accounts an administrator creates, changes, approves or deletes.

Ids are stable forever: rows outlive the code. ``details`` carry enumerated values and changed field names
only, never a field's value.
"""

from enum import StrEnum
from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class UserCreateMethod(StrEnum):
    """How an account came to exist.

    Attributes:
        ADMIN: An administrator created it.
        SIGN_UP: The person signed up.
        IDENTITY_PROVIDER: A sign-in provider created it on first sign-in.
        ONBOARDING: It is the first administrator of a fresh installation.
    """

    ADMIN = "admin"
    SIGN_UP = "sign_up"
    IDENTITY_PROVIDER = "identity_provider"
    ONBOARDING = "onboarding"


class UserCreateDetails(VersionedPayload):
    """Details of ``users.user.create``.

    Attributes:
        access_type: The access tier the account was created with.
        method: How the account was created.
        invited: Whether an administrator created it without a password and mailed its owner an invitation to
            choose one.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 3

    access_type: str
    method: UserCreateMethod
    invited: bool = False


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

USER_PURGE = jasil_audit.AuditAction(
    id="users.user.purge",
    category=jasil_audit.Category.SYSTEM,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.users.user.purge",
    description_default="An unverified sign-up was removed after its verification link expired",
)

USER_EMAIL_CHANGE = jasil_audit.AuditAction(
    id="users.email.change",
    category=jasil_audit.Category.IDENTITY,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.users.email.change",
    description_default="An account's email address was changed",
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (
    USER_CREATE,
    USER_UPDATE,
    USER_APPROVE,
    USER_DELETE,
    USER_PURGE,
    USER_EMAIL_CHANGE,
)
