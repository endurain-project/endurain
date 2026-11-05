"""Scheduled work owned by identity providers."""

import jasil.runtime as platform_runtime

import core.database as core_database
import core.scheduler as core_scheduler
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.icon_service as idp_icon_service
import modules.auth.identity_providers.provider_service as idp_provider_service

ICON_SWEEP_LOCK_NAME = "identity_providers_icon_sweep"
REENCRYPT_LOCK_NAME = "identity_providers_reencrypt"


def sweep_unreferenced_icons() -> None:
    """Delete icon blobs no identity provider names any more.

    Scheduler-invoked, with no request to carry the provider, so this entry point resolves it; the
    scheduler's lock keeps it to one replica.
    """
    idp_icon_service.sweep_unreferenced_icons(platform_runtime.get_active_platform().storage)


def reencrypt_stored_secrets() -> None:
    """Re-encrypt the provider client credentials under the first FERNET_KEY; does nothing while one key is configured."""
    with core_database.SessionLocal() as db:
        idp_provider_service.reencrypt_stored_secrets(db)


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return the icon sweep.

    Returns:
        The jobs to schedule.
    """
    return (
        core_scheduler.ScheduledJob(
            sweep_unreferenced_icons,
            idp_constants.ICON_SWEEP_INTERVAL_MINUTES,
            "remove identity provider icons no provider names",
            lock_name=ICON_SWEEP_LOCK_NAME,
        ),
    )
