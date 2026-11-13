"""Scheduled work owned by identity providers."""

import jasil.runtime as platform_runtime

import core.config as core_config
import core.database as core_database
import core.scheduler as core_scheduler
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.icon_service as idp_icon_service
import modules.auth.identity_providers.oidc_client_service as idp_oidc_client
import modules.auth.identity_providers.provider_service as idp_provider_service
import modules.auth.identity_providers.token_revocation_service as idp_token_revocation_service

ICON_SWEEP_LOCK_NAME = "identity_providers_icon_sweep"
REENCRYPT_LOCK_NAME = "identity_providers_reencrypt"
REVOCATION_SWEEP_LOCK_NAME = "identity_providers_token_revocation_sweep"


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


def revoke_ended_session_tokens() -> None:
    """Revoke at their providers the tokens of sessions that ended without an event reaching the subscriber.

    Covers expired and purged sessions, and revocations whose event was lost or whose provider was unreachable;
    the scheduler's lock keeps it to one replica.
    """
    oidc = idp_oidc_client.OidcClientService(platform_runtime.get_state(), core_config.API_VERSION)
    idp_token_revocation_service.IdpTokenRevocationService(oidc).revoke_ended_sessions()


def recurring_jobs() -> tuple[core_scheduler.ScheduledJob, ...]:
    """Return the icon sweep and the token-revocation sweep.

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
        core_scheduler.ScheduledJob(
            revoke_ended_session_tokens,
            idp_constants.TOKEN_REVOCATION_SWEEP_INTERVAL_MINUTES,
            "revoke identity provider tokens of ended sessions",
            lock_name=REVOCATION_SWEEP_LOCK_NAME,
        ),
    )
