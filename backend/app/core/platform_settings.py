"""Translate Endurain's settings into the substrate's configuration object.

JASIL never reads environment variables: the host builds a
:class:`~jasil.settings.JasilSettings` from whatever source it likes and installs
it once at startup. :data:`core.config.settings` stays the single place an
operator-facing variable is declared, documented, and validated; this module is
the one seam that maps those variables onto the substrate's shape.

The capability URIs come from ``core.config``'s ``substrate_*_uri`` properties
rather than its ``resolved_*`` ones. Those are the values the substrate is meant
to see — deliberately *not* folding in the ``local`` fallbacks, so a
``distributed`` or ``custom`` profile still presents an unset URI and JASIL still
refuses to guess one. ``core.config`` owns that distinction (and validates it in
``Settings._enforce_deployment_topology``) so the rule is stated once, next to
the variables it is about, instead of half here and half there.
"""

import jasil.profile as jasil_profile
import jasil.settings as jasil_settings

import core.config as core_config

#: The Redis Pub/Sub channel carrying realtime hints, namespaced to Endurain.
REALTIME_CHANNEL = "endurain:realtime"


def build_jasil_settings(settings: core_config.Settings) -> jasil_settings.JasilSettings:
    """Build the substrate configuration from the application settings.

    Args:
        settings: The application settings to translate.

    Returns:
        The equivalent :class:`~jasil.settings.JasilSettings`.
    """
    return jasil_settings.JasilSettings(
        profile=jasil_profile.DeploymentProfile(settings.DEPLOYMENT_PROFILE.value),
        web_workers=settings.WEB_WORKERS,
        enforce_deployment_consistency=settings.ENVIRONMENT != "development",
        data_dir=settings.DATA_DIR,
        state_uri=settings.substrate_state_uri,
        storage_uri=settings.substrate_storage_uri,
        events_uri=settings.substrate_events_uri,
        lock_uri=settings.substrate_lock_uri,
        # Redis Pub/Sub channels are server-wide, so a deployment names its own.
        realtime_channel=REALTIME_CHANNEL,
        jobs=_build_job_settings(settings),
        job_worker_mode=settings.job_worker_mode,
        event_log=jasil_settings.EventLogSettings(
            enabled=settings.EVENT_LOG_ENABLED,
            retention_days=settings.EVENT_LOG_RETENTION_DAYS,
        ),
        # Endurain wrote objects in the flat ``{data_dir}/{area}/{key}`` layout.
        storage=jasil_settings.StorageSettings(local_legacy_layout=True),
        network=jasil_settings.NetworkSettings(ssrf_allowed_hosts=tuple(settings.SSRF_ALLOWED_HOSTS)),
    )


def _build_job_settings(settings: core_config.Settings) -> jasil_settings.JobSettings:
    """Map the durable-job variables onto ``JobSettings``."""
    return jasil_settings.JobSettings(
        enabled=settings.JOBS_ENABLED,
        lease_seconds=settings.JOBS_LEASE_SECONDS,
        batch_size=settings.JOBS_BATCH_SIZE,
        backoff_base_seconds=settings.JOBS_BACKOFF_BASE_SECONDS,
        backoff_max_seconds=settings.JOBS_BACKOFF_MAX_SECONDS,
        poll_interval_seconds=settings.JOBS_POLL_INTERVAL_SECONDS,
        max_attempts=settings.JOBS_MAX_ATTEMPTS,
        retention_days=settings.JOBS_RETENTION_DAYS,
    )
