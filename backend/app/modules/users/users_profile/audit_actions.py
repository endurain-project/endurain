"""Audit actions written by the users-profile package.

They cover the user's own profile, privacy, username-change and email-change requests, and the profile export and import.

Ids are stable forever: rows outlive the code. ``details`` carry changed field names and flags only, never a
field's value, a username, an email address or a file name.
"""

from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class ProfileUpdateDetails(VersionedPayload):
    """Details of ``users.profile.update``.

    Attributes:
        changed_fields: The names of the profile fields whose value changed.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    changed_fields: list[str]


class PrivacyUpdateDetails(VersionedPayload):
    """Details of ``users.privacy.update``.

    Attributes:
        changed_fields: The names of the privacy settings whose value changed.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    changed_fields: list[str]


class EmailChangeRequestDetails(VersionedPayload):
    """Details of ``users.email.change_request``.

    Attributes:
        confirmation_required: Whether the new address waits for a confirmation link; False when it was applied
            at once because the server cannot send mail.
        other_sessions_revoked: Whether the user's other sessions were signed out with the request.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    confirmation_required: bool
    other_sessions_revoked: bool


class UsernameChangeDetails(VersionedPayload):
    """Details of ``users.username.change``.

    Attributes:
        other_sessions_revoked: Whether the user's other sessions were signed out with the change.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    other_sessions_revoked: bool


PROFILE_UPDATE = jasil_audit.AuditAction(
    id="users.profile.update",
    category=jasil_audit.Category.IDENTITY,
    severity=jasil_audit.Severity.LOW,
    description_key="audit.users.profile.update",
    description_default="A user changed their profile",
    details_model=ProfileUpdateDetails,
)

PRIVACY_UPDATE = jasil_audit.AuditAction(
    id="users.privacy.update",
    category=jasil_audit.Category.AUTHORIZATION,
    severity=jasil_audit.Severity.LOW,
    description_key="audit.users.privacy.update",
    description_default="A user changed their privacy settings",
    details_model=PrivacyUpdateDetails,
)

EMAIL_CHANGE_REQUEST = jasil_audit.AuditAction(
    id="users.email.change_request",
    category=jasil_audit.Category.IDENTITY,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.users.email.change_request",
    description_default="A user requested an email address change",
    details_model=EmailChangeRequestDetails,
)

USERNAME_CHANGE = jasil_audit.AuditAction(
    id="users.username.change",
    category=jasil_audit.Category.IDENTITY,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.users.username.change",
    description_default="A user changed their username",
    details_model=UsernameChangeDetails,
)

PROFILE_EXPORT_REQUEST = jasil_audit.AuditAction(
    id="users.profile_export.request",
    category=jasil_audit.Category.DATA_TRANSFER,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.users.profile_export.request",
    description_default="A user requested an export of their data",
)

PROFILE_EXPORT_DOWNLOAD = jasil_audit.AuditAction(
    id="users.profile_export.download",
    category=jasil_audit.Category.DATA_TRANSFER,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.users.profile_export.download",
    description_default="A user downloaded an export of their data",
)

PROFILE_IMPORT_REQUEST = jasil_audit.AuditAction(
    id="users.profile_import.request",
    category=jasil_audit.Category.DATA_TRANSFER,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.users.profile_import.request",
    description_default="A user requested an import of their data",
)

PROFILE_IMPORT_COMPLETE = jasil_audit.AuditAction(
    id="users.profile_import.complete",
    category=jasil_audit.Category.DATA_TRANSFER,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.users.profile_import.complete",
    description_default="An import of a user's data ended",
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (
    PROFILE_UPDATE,
    PRIVACY_UPDATE,
    EMAIL_CHANGE_REQUEST,
    USERNAME_CHANGE,
    PROFILE_EXPORT_REQUEST,
    PROFILE_EXPORT_DOWNLOAD,
    PROFILE_IMPORT_REQUEST,
    PROFILE_IMPORT_COMPLETE,
)
