"""Strava account linking: the OAuth state is checked on the request, the code exchange runs off it."""

import jasil.audit as jasil_audit

import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.sync_runner as core_sync_runner
import modules.strava.audit_actions as strava_audit_actions
import modules.strava.client_service as strava_client_service
import modules.strava.constants as strava_constants
import modules.strava.oauth_state_store as strava_oauth_state_store
import modules.strava.schema as strava_schema
import modules.strava.sync_state_store as strava_sync_state_store
import modules.users.users_integrations.integration_service as user_integrations_integration

logger = core_logger.get_logger(__name__)

# The exchange runs here, not on the request threadpool: it is a Strava round trip, and a few users
# linking at once must not leave the API without worker threads. It is a pool and not a durable job
# because the one-time authorization code is never written to a job row, and a consumed code cannot
# be retried.
_link_pool = core_sync_runner.link_pool("strava-link")


def shutdown_link_pool(*, wait: bool = False) -> None:
    """Stop accepting links and release the pool threads.

    Args:
        wait: Whether to wait for links still running.
    """
    _link_pool.shutdown(wait=wait)


def start_link(
    user_id: int,
    link: strava_schema.StravaLinkRequest,
    oauth_states: strava_oauth_state_store.StravaOAuthStateStore,
    states: strava_sync_state_store.StravaSyncStateStore,
) -> strava_schema.StravaSyncStatus:
    """Check the OAuth callback and queue the exchange of its code for tokens.

    The state is consumed first, so a callback is accepted once and only for the user who stored
    it. The stored client credentials survive a failed exchange, so the user can retry without
    entering them again. Poll ``GET /strava/sync/link`` for the outcome.

    Args:
        user_id: The authenticated user.
        link: The state, authorization code and granted scopes Strava returned.
        oauth_states: The one-time OAuth state store.
        states: Shared store of the link's state.

    Returns:
        The link's initial status.

    Raises:
        ProviderScopeInsufficientError: When the granted scopes lack one the link needs; the state is left unused.
        PoolFullError: When every link slot of this process is busy; the state is left unused.
        InvalidInputError: When the state is unknown or expired, or the user has not stored a client ID and secret.
        ConflictError: When a link is already in progress for the user.
    """
    granted = set(link.scope.split(","))
    missing = [scope for scope in strava_constants.REQUIRED_OAUTH_SCOPES if scope not in granted]
    if missing:
        logger.warning(
            "Strava link refused: missing scopes <scopes>",
            extra=core_logger.context(user_id=user_id, scopes=missing),
        )
        _audit_link_failure(user_id, strava_audit_actions.LinkFailureReason.INSUFFICIENT_SCOPE)
        raise core_exceptions.ProviderScopeInsufficientError(
            f"Strava did not grant every required permission; missing: {', '.join(missing)}"
        )
    # Checked before the state is used up, so a refused link can be retried with the same callback.
    _link_pool.require_capacity()
    if not oauth_states.consume(user_id, link.state):
        logger.warning("Strava link refused: unknown or expired state", extra=core_logger.context(user_id=user_id))
        raise core_exceptions.InvalidInputError("The Strava link state is invalid or has expired")
    with core_database.SessionLocal() as db:
        user_integrations = user_integrations_integration.get_user_integrations(user_id, db)
    if (
        user_integrations is None
        or user_integrations.strava_client_id is None
        or user_integrations.strava_client_secret is None
    ):
        raise core_exceptions.InvalidInputError("Strava client ID and secret not set")
    core_sync_runner.start_claimed(
        lambda: states.begin(user_id, strava_constants.SyncKind.LINK),
        "A Strava link is already in progress",
        lambda: _link_pool.submit(run_link, user_id, link.code, states),
        lambda: states.set_status(user_id, strava_constants.SyncKind.LINK, strava_constants.SyncStatus.FAILED),
        status_route="strava_sync_status",
        status_params={"kind": strava_constants.SyncKind.LINK.value},
    )
    logger.info("Strava link queued", extra=core_logger.context(user_id=user_id))
    return strava_schema.StravaSyncStatus(
        kind=strava_constants.SyncKind.LINK, status=strava_constants.SyncStatus.QUEUED
    )


def _record_refused_link(user_id: int, err: Exception) -> None:
    """Record that Strava refused the link, when ``err`` is a refusal.

    Any other error, such as a server error or a bug, is not Strava refusing the code and leaves no row.

    Args:
        user_id: The user linking Strava.
        err: What the exchange raised.
    """
    if strava_client_service.is_strava_rate_limit_error(err):
        reason = strava_audit_actions.LinkFailureReason.TOO_MANY_REQUESTS
    elif strava_client_service.is_strava_unauthorized_error(err):
        reason = strava_audit_actions.LinkFailureReason.UNAUTHORIZED
    elif strava_client_service.is_strava_client_error(err):
        reason = strava_audit_actions.LinkFailureReason.REJECTED
    else:
        return
    _audit_link_failure(user_id, reason)


def _audit_link_failure(user_id: int, reason: strava_audit_actions.LinkFailureReason) -> None:
    """Record a refused link.

    Args:
        user_id: The user linking Strava.
        reason: Why the link was refused.
    """
    jasil_audit.record_detached(
        strava_audit_actions.ACCOUNT_LINK,
        outcome=jasil_audit.Outcome.FAILURE,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
        details=strava_audit_actions.LinkFailureDetails(reason=reason),
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
        with core_database.SessionLocal() as db:
            user_integrations = user_integrations_integration.require_user_integrations(user_id, db)
        answer = strava_client_service.create_strava_client(user_integrations).exchange_code_for_token(
            # Stored from the positive integer the credentials form accepts.
            client_id=int(strava_client_service.get_client_id(user_integrations)),
            client_secret=strava_client_service.get_client_secret(user_integrations),
            code=code,
        )
        # stravalib also types the answer to a request for the athlete; this one asks only for the tokens.
        tokens = answer[0] if isinstance(answer, tuple) else answer
        with core_database.SessionLocal() as db:
            user_integrations_integration.link_strava_account(user_id, tokens, db)
            jasil_audit.stage(
                db,
                strava_audit_actions.ACCOUNT_LINK,
                target_type="user",
                target_id=str(user_id),
                target_owner_id=str(user_id),
            )
            db.commit()
    except Exception as err:
        logger.warning("Unable to link Strava account", extra=core_logger.context(user_id=user_id), exc_info=err)
        _record_refused_link(user_id, err)
        states.set_status(user_id, kind, strava_constants.SyncStatus.FAILED)
        return
    states.set_status(user_id, kind, strava_constants.SyncStatus.COMPLETED)
    logger.info("Strava linked", extra=core_logger.context(user_id=user_id))
