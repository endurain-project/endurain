"""Scheduled cleanup for expired identity-provider link tokens."""

import core.database as core_database
import core.logger as core_logger
import core.scheduler as core_scheduler
import modules.auth.identity_provider_link_tokens.service as idp_link_token_service

logger = core_logger.get_logger(__name__)

PURGE_LOCK_NAME = "auth_identity_provider_link_tokens_purge"


def delete_expired_tokens_from_db() -> None:
    """Delete expired one-time link tokens, one bounded batch per transaction."""
    with core_database.SessionLocal() as db:
        deleted_count = idp_link_token_service.delete_expired_tokens(db)
    if deleted_count:
        logger.info("Deleted expired identity-provider link tokens", extra=core_logger.context(count=deleted_count))


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return recurring identity-provider link-token cleanup work."""
    return (
        core_scheduler.ScheduledJob(
            delete_expired_tokens_from_db,
            5,
            "delete expired IdP link tokens from the database",
            lock_name=PURGE_LOCK_NAME,
        ),
    )
