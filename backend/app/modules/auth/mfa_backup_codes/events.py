"""Domain event channels owned by the MFA backup-codes package.

Payloads carry the user and a count only: events are persisted, so a backup code is never put in one.
"""

import uuid
from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

# Published after a backup code was used to pass an MFA check, so its owner is told.
BACKUP_CODE_USED = "auth.backup_code_used"


class BackupCodeUsedPayload(VersionedPayload):
    """Validated payload for the ``auth.backup_code_used`` event.

    Attributes:
        user_id: The user whose backup code was used.
        backup_codes_remaining: How many unused backup codes the user has left.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: uuid.UUID
    backup_codes_remaining: int
