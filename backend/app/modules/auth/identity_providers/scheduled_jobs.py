"""Scheduled work owned by identity providers."""

import jasil.runtime as platform_runtime

import core.scheduler as core_scheduler
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.icon_service as idp_icon_service

ICON_SWEEP_LOCK_NAME = "identity_providers_icon_sweep"


def sweep_unreferenced_icons() -> None:
    """Delete icon blobs no identity provider names any more.

    Scheduler-invoked, with no request to carry the provider, so this entry point resolves it; the
    scheduler's lock keeps it to one replica.
    """
    idp_icon_service.sweep_unreferenced_icons(platform_runtime.get_active_platform().storage)


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
