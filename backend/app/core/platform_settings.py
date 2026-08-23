"""Translate Endurain's settings into the substrate's configuration object.

JASIL never reads environment variables: the host builds a
:class:`~jasil.settings.JasilSettings` from whatever source it likes and installs
it once at startup. :data:`core.config.settings` stays the single place an
operator-facing variable is declared, documented, and validated; this module is
the one seam that maps those variables onto the substrate's shape.

Two mappings are deliberate rather than mechanical:

* **Capability URIs are passed unresolved.** ``core.config`` exposes
  ``resolved_*`` properties that already fold in the ``local`` defaults, but
  handing those to JASIL would mean the ``distributed`` profile never sees an
  unset URI and so never refuses to guess one — the fail-fast that stops every
  replica silently keeping its own copy of shared state.
* **The coordination lock keeps its host-side default.** JASIL defaults
  ``lock_uri`` to ``noop://`` for the whole ``local`` profile, but Endurain
  defaults it to ``postgres-advisory://`` as soon as the topology runs more than
  one process, so a multi-worker ``local`` deployment coordinates its scheduled
  jobs without the operator setting anything. Resolving it here preserves that.
"""

import jasil.profile as jasil_profile
import jasil.settings as jasil_settings

import core.config as core_config


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
        data_dir=settings.DATA_DIR,
        state_uri=settings.STATE_URI or settings.REDIS_URL or None,
        storage_uri=settings.STORAGE_URI or None,
        events_uri=settings.EVENTS_URI or settings.REDIS_URL or None,
        lock_uri=_resolve_lock_uri(settings),
        jobs=_build_job_settings(settings),
        event_log=jasil_settings.EventLogSettings(
            enabled=settings.EVENT_LOG_ENABLED,
            retention_days=settings.EVENT_LOG_RETENTION_DAYS,
        ),
        geocoding=_build_geocoding_settings(settings),
        network=jasil_settings.NetworkSettings(ssrf_allowed_hosts=tuple(settings.SSRF_ALLOWED_HOSTS)),
    )


def _resolve_lock_uri(settings: core_config.Settings) -> str | None:
    """Resolve the coordination lock, keeping Endurain's multi-process default."""
    if settings.LOCK_URI:
        return settings.LOCK_URI
    if settings.resolved_deployment_topology.requires_shared_state:
        return "postgres-advisory://"
    return None


def _build_job_settings(settings: core_config.Settings) -> jasil_settings.JobSettings:
    """Map the durable-job variables onto ``JobSettings``."""
    return jasil_settings.JobSettings(
        enabled=settings.JOBS_ENABLED,
        lease_seconds=settings.JOBS_LEASE_SECONDS,
        batch_size=settings.JOBS_BATCH_SIZE,
        # JASIL types both backoff bounds as whole seconds; sub-second tuning was
        # never meaningful for a retry delay measured in minutes.
        backoff_base_seconds=int(settings.JOBS_BACKOFF_BASE_SECONDS),
        backoff_max_seconds=int(settings.JOBS_BACKOFF_MAX_SECONDS),
        poll_interval_seconds=settings.JOBS_POLL_INTERVAL_SECONDS,
        max_attempts=settings.JOBS_MAX_ATTEMPTS,
        retention_days=settings.JOBS_RETENTION_DAYS,
    )


def _build_geocoding_settings(settings: core_config.Settings) -> jasil_settings.GeocodingSettings:
    """Map the reverse-geocoding variables onto ``GeocodingSettings``.

    The ``changeme`` placeholder becomes an unset key so JASIL disables the
    capability for the same reason the previous container did.
    """
    api_key = settings.GEOCODES_MAPS_API
    return jasil_settings.GeocodingSettings(
        provider=settings.REVERSE_GEO_PROVIDER,
        rate_limit=settings.REVERSE_GEO_RATE_LIMIT,
        api_key=None if api_key == "changeme" else api_key,
        nominatim_host=settings.NOMINATIM_API_HOST,
        nominatim_use_https=settings.NOMINATIM_API_USE_HTTPS,
        photon_host=settings.PHOTON_API_HOST,
        photon_use_https=settings.PHOTON_API_USE_HTTPS,
        user_agent=f"Endurain/{core_config.API_VERSION} (ReverseGeocoding)",
    )
