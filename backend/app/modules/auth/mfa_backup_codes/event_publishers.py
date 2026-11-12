"""Publish the MFA backup-codes domain events through the platform publish facade."""

import jasil.publisher as platform_publisher
from sqlalchemy.orm import Session

import core.event_metadata as core_event_metadata
import modules.auth.mfa_backup_codes.events as mfa_backup_codes_events


def publish_backup_code_used(user_id: int, backup_codes_remaining: int, db: Session) -> None:
    """Stage ``auth.backup_code_used`` in the caller's transaction.

    Args:
        user_id: The user whose backup code was used.
        backup_codes_remaining: How many unused backup codes the user has left.
        db: The producer's DB session; the event is published when it commits.
    """
    payload = mfa_backup_codes_events.BackupCodeUsedPayload(
        user_id=user_id, backup_codes_remaining=backup_codes_remaining
    )
    platform_publisher.publish_on_commit(
        mfa_backup_codes_events.BACKUP_CODE_USED,
        payload.model_dump(mode="json"),
        source="api:mfa_backup_codes",
        metadata={core_event_metadata.META_USER_ID: user_id},
        db=db,
        schema_version=payload.SCHEMA_VERSION,
    )
