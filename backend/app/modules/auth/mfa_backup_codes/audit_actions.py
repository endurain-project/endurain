"""Audit actions written by the MFA backup-codes package.

Ids are stable forever: rows outlive the code. ``details`` never carry a code.
"""

from typing import ClassVar

import jasil.audit as jasil_audit
from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict


class BackupCodeUseDetails(VersionedPayload):
    """Details of ``auth.backup_codes.use``.

    Attributes:
        remaining_codes: How many unused backup codes the user has left after this one.
    """

    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    remaining_codes: int


BACKUP_CODE_USE = jasil_audit.AuditAction(
    id="auth.backup_codes.use",
    category=jasil_audit.Category.CREDENTIAL,
    severity=jasil_audit.Severity.MEDIUM,
    description_key="audit.auth.backup_codes.use",
    description_default="A backup code was used",
    details_model=BackupCodeUseDetails,
)

#: Every action this package writes, registered by the composition root.
ACTIONS: tuple[jasil_audit.AuditAction, ...] = (BACKUP_CODE_USE,)
