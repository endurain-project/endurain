"""Audit actions written by the server-settings package.

Ids are stable forever: rows outlive the code. ``details`` carry changed field names only, never a setting's
value.
"""

from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class SettingsChangeDetails(VersionedPayload):
    """Details of an action that changes settings fields.

    Attributes:
        changed_fields: The names of the fields whose value changed.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    changed_fields: list[str]


SETTINGS_UPDATE = jasil_audit.AuditAction(
    id="server_settings.settings.update",
    category=jasil_audit.Category.ADMIN,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.server_settings.settings.update",
    description_default="An administrator changed the server settings",
    details_model=SettingsChangeDetails,
)

MAIL_UPDATE = jasil_audit.AuditAction(
    id="server_settings.mail.update",
    category=jasil_audit.Category.ADMIN,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.server_settings.mail.update",
    description_default="An administrator changed the mail settings",
    details_model=SettingsChangeDetails,
)

LOGIN_PHOTO_UPDATE = jasil_audit.AuditAction(
    id="server_settings.login_photo.update",
    category=jasil_audit.Category.ADMIN,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.server_settings.login_photo.update",
    description_default="An administrator replaced the login page photo",
)

LOGIN_PHOTO_DELETE = jasil_audit.AuditAction(
    id="server_settings.login_photo.delete",
    category=jasil_audit.Category.ADMIN,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.server_settings.login_photo.delete",
    description_default="An administrator removed the login page photo",
)

LOGS_CLEAR = jasil_audit.AuditAction(
    id="server_settings.logs.clear",
    category=jasil_audit.Category.ADMIN,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.server_settings.logs.clear",
    description_default="An administrator cleared the server logs",
)

LOGS_DOWNLOAD = jasil_audit.AuditAction(
    id="server_settings.logs.download",
    category=jasil_audit.Category.DATA_TRANSFER,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.server_settings.logs.download",
    description_default="An administrator downloaded the server log",
)

SETTINGS_IMPORT = jasil_audit.AuditAction(
    id="server_settings.settings.import",
    category=jasil_audit.Category.SYSTEM,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.server_settings.settings.import",
    description_default="Deprecated environment settings were imported at startup",
    details_model=SettingsChangeDetails,
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (
    SETTINGS_UPDATE,
    MAIL_UPDATE,
    LOGIN_PHOTO_UPDATE,
    LOGIN_PHOTO_DELETE,
    LOGS_CLEAR,
    LOGS_DOWNLOAD,
    SETTINGS_IMPORT,
)
