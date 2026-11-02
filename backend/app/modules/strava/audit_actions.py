"""Audit actions written by the Strava package: the client, the account link and the gear import.

Ids are stable forever: rows outlive the code. ``details`` carry enumerated values and counts only, never the
client id or secret, a code, a token, a provider message or a file's content.
"""

from enum import StrEnum
from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class LinkFailureReason(StrEnum):
    """Why Strava refused to link an account.

    Attributes:
        UNAUTHORIZED: Strava answered 401: the client id or secret was not accepted.
        REJECTED: Strava refused the request with another 4xx answer, such as an invalid or used code.
        TOO_MANY_REQUESTS: Strava is rate limiting the application.
    """

    UNAUTHORIZED = "unauthorized"
    REJECTED = "rejected"
    TOO_MANY_REQUESTS = "too_many_requests"


class GearImportType(StrEnum):
    """Which Strava export file the gear came from."""

    BIKES = "bikes"
    SHOES = "shoes"


class LinkFailureDetails(VersionedPayload):
    """Details of ``strava.account.link``.

    Attributes:
        reason: Why Strava refused the link; None on success.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    reason: LinkFailureReason | None = None


class GearImportDetails(VersionedPayload):
    """Details of ``strava.gear.import``.

    Attributes:
        gear_type: Which export file was imported.
        count: How many gear entries were handed to the gear module.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    gear_type: GearImportType
    count: int


CLIENT_UPDATE = jasil_audit.AuditAction(
    id="strava.client.update",
    category=jasil_audit.Category.INTEGRATION,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.strava.client.update",
    description_default="A Strava API client was stored",
)

ACCOUNT_LINK = jasil_audit.AuditAction(
    id="strava.account.link",
    category=jasil_audit.Category.INTEGRATION,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.strava.account.link",
    description_default="A Strava account was linked",
    details_model=LinkFailureDetails,
)

ACCOUNT_UNLINK = jasil_audit.AuditAction(
    id="strava.account.unlink",
    category=jasil_audit.Category.INTEGRATION,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.strava.account.unlink",
    description_default="A Strava account unlink was requested",
)

ACCOUNT_REVOKE = jasil_audit.AuditAction(
    id="strava.account.revoke",
    category=jasil_audit.Category.INTEGRATION,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.strava.account.revoke",
    description_default="A Strava account was unlinked because Strava rejected its token",
)

GEAR_IMPORT = jasil_audit.AuditAction(
    id="strava.gear.import",
    category=jasil_audit.Category.DATA_TRANSFER,
    severity=jasil_audit.Severity.LOW,
    description_key="audit.strava.gear.import",
    description_default="Gear was imported from a Strava export",
    details_model=GearImportDetails,
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (
    CLIENT_UPDATE,
    ACCOUNT_LINK,
    ACCOUNT_UNLINK,
    ACCOUNT_REVOKE,
    GEAR_IMPORT,
)
