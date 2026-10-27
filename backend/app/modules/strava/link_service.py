"""Strava account linking: the OAuth state is checked on the request, the code exchange runs off it."""

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import core.local_pool as core_local_pool
import core.logger as core_logger
import modules.strava.client_service as strava_client_service
import modules.strava.constants as strava_constants
import modules.strava.oauth_state_store as strava_oauth_state_store
import modules.strava.schema as strava_schema
import modules.strava.sync_state_store as strava_sync_state_store
import modules.users.users_integrations.integration_service as user_integrations_integration
import modules.websocket.integration_service as websocket_integration
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)

# The exchange runs here, not on the request threadpool: it is a Strava round trip, and a few users
# linking at once must not leave the API without worker threads. It is a pool and not a durable job
# because the one-time authorization code is never written to a job row, and a consumed code cannot
# be retried. A link past this capacity is refused rather than queued.
_link_pool = core_local_pool.BoundedPool(
    "strava-link", workers=strava_constants.MAX_CONCURRENT_LINKS, max_pending=strava_constants.MAX_CONCURRENT_LINKS
)


def shutdown_link_pool(*, wait: bool = False) -> None:
    """Stop accepting links and release the pool threads.

    Args:
        wait: Whether to wait for links still running.
    """
    _link_pool.shutdown(wait=wait)


def start_link(
    link: strava_schema.StravaLinkRequest,
    user_id: int,
    oauth_states: strava_oauth_state_store.StravaOAuthStateStore,
    states: strava_sync_state_store.StravaSyncStateStore,
) -> strava_schema.StravaSyncStatus:
    """Check the OAuth callback and queue the exchange of its code for tokens.

    The state is consumed first, so a callback is accepted once and only for the user who stored
    it. The stored client credentials survive a failed exchange, so the user can retry without
    entering them again. Poll ``GET /strava/sync/link`` for the outcome.

    Args:
        link: The state and authorization code Strava returned.
        user_id: The authenticated user.
        oauth_states: The one-time OAuth state store.
        states: Shared store of the link's state.

    Returns:
        The link's initial status.

    Raises:
        PoolFullError: When every link slot of this process is busy; the state is left unused.
        InvalidInputError: When the state is unknown or expired, or the user has not stored a client ID and secret.
        ConflictError: When a link is already in progress for the user.
    """
    # Checked before the state is used up, so a refused link can be retried with the same callback.
    _link_pool.require_capacity()
    if not oauth_states.consume(user_id, link.state):
        logger.warning("Strava link refused: unknown or expired state", extra=core_logger.context(user_id=user_id))
        raise core_exceptions.InvalidInputError("The Strava link state is invalid or has expired")
    with SessionLocal() as db:
        user_integrations = user_integrations_integration.get_user_integrations(user_id, db)
    if (
        user_integrations is None
        or user_integrations.strava_client_id is None
        or user_integrations.strava_client_secret is None
    ):
        raise core_exceptions.InvalidInputError("Strava client ID and secret not set")
    if not states.begin(user_id, strava_constants.SyncKind.LINK):
        raise core_exceptions.ConflictError("A Strava link is already in progress")
    try:
        _link_pool.submit(run_link, user_id, link.code, states)
    except BaseException:
        # The link never started, so nothing else would finish its claim.
        states.set_status(user_id, strava_constants.SyncKind.LINK, strava_constants.SyncStatus.FAILED)
        raise
    logger.info("Strava link queued", extra=core_logger.context(user_id=user_id))
    return strava_schema.StravaSyncStatus(
        kind=strava_constants.SyncKind.LINK, status=strava_constants.SyncStatus.QUEUED
    )


def run_link(user_id: int, code: str, states: strava_sync_state_store.StravaSyncStateStore) -> None:
    """Exchange an authorization code for tokens, store them and record the outcome.

    Blocking; runs on the link pool, never on a request. The exchange is one bounded Strava
    call made with no database session open. A failure is recorded as ``FAILED`` and logged,
    not raised: a consumed code cannot be retried.

    Args:
        user_id: The user linking Strava.
        code: The authorization code Strava returned.
        states: Shared store of the link's state.
    """
    kind = strava_constants.SyncKind.LINK
    states.set_status(user_id, kind, strava_constants.SyncStatus.RUNNING)
    try:
        with SessionLocal() as db:
            user_integrations = user_integrations_integration.get_user_integrations(user_id, db)
        tokens = strava_client_service.create_strava_client(user_integrations).exchange_code_for_token(
            client_id=core_cryptography.decrypt_token_fernet(user_integrations.strava_client_id),
            client_secret=core_cryptography.decrypt_token_fernet(user_integrations.strava_client_secret),
            code=code,
        )
        with SessionLocal() as db:
            user_integrations_integration.link_strava_account(user_id, tokens, db)
            db.commit()
    except Exception as err:
        logger.error("Unable to link Strava account", extra=core_logger.context(user_id=user_id), exc_info=err)
        states.set_status(user_id, kind, strava_constants.SyncStatus.FAILED)
        websocket_integration.push_job_changed(user_id, strava_constants.LINK_JOB)
        return
    states.set_status(user_id, kind, strava_constants.SyncStatus.COMPLETED)
    websocket_integration.push_job_changed(user_id, strava_constants.LINK_JOB)
    logger.info("Strava linked", extra=core_logger.context(user_id=user_id))
