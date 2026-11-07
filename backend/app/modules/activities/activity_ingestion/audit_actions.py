"""Audit actions written by the activity-ingestion package: bulk imports a user queues.

Ids are stable forever: rows outlive the code. ``details`` carry counts and enumerated values only, never a
file, folder or archive name.
"""

from enum import StrEnum
from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class ImportSource(StrEnum):
    """Where a bulk import reads its files from.

    Attributes:
        ARCHIVE: An archive the user uploaded.
        SERVER_DIRECTORY: The user's import folder on the server.
    """

    ARCHIVE = "archive"
    SERVER_DIRECTORY = "server_directory"


class ImportRequestDetails(VersionedPayload):
    """Details of ``activities.import.request``.

    Attributes:
        source: Where the files come from.
        file_count: How many importable files the request found, or None when it is not known until the
            files are packed.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    source: ImportSource
    file_count: int | None


IMPORT_REQUEST = jasil_audit.AuditAction(
    id="activities.import.request",
    category=jasil_audit.Category.DATA_TRANSFER,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.activities.import.request",
    description_default="A bulk activity import was requested",
    details_model=ImportRequestDetails,
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (IMPORT_REQUEST,)
