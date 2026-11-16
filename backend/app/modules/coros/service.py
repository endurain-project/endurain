"""Application service for the COROS connection lifecycle and sync state."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.timezone as core_timezone
import modules.coros.constants as coros_constants
import modules.coros.contracts as coros_contracts
import modules.coros.crud as coros_crud
import modules.coros.oauth as coros_oauth
import modules.coros.schema as coros_schema

logger = core_logger.get_logger(__name__)


def _metadata_from_data(data: coros_schema.CorosIntegrationData) -> coros_contracts.CorosOAuthMetadata:
    """Rebuild OAuth metadata from a stored integration.

    Args:
        data: Stored integration state.

    Returns:
        The metadata needed to refresh or revoke tokens.

    Raises:
        coros_oauth.CorosAuthenticationError: When the stored connection is
            incomplete and the user must reconnect.
    """
    if not data.issuer or not data.mcp_url:
        raise coros_oauth.CorosAuthenticationError("COROS connection must be renewed")
    return coros_contracts.CorosOAuthMetadata(
        issuer=data.issuer,
        authorization_endpoint=f"{data.issuer.rstrip('/')}/oauth2/authorize",
        token_endpoint=f"{data.issuer.rstrip('/')}/oauth2/token",
        revocation_endpoint=f"{data.issuer.rstrip('/')}/oauth2/revoke",
        registration_endpoint=f"{data.issuer.rstrip('/')}/connect/register",
        mcp_url=data.mcp_url,
        scopes=tuple((data.scope or coros_constants.SCOPE_STRING).split()),
    )


def begin_authorization(user_id: int, redirect_uri: str, db: Session) -> str:
    """Start a COROS OAuth authorization.

    Reuses the user's dynamically registered client when it belongs to the same
    issuer and callback URI; otherwise registers a new public client.

    Args:
        user_id: Authenticated user.
        redirect_uri: Endurain callback URI.
        db: Database session.

    Returns:
        The authorization URL to open in the browser.

    Raises:
        coros_oauth.CorosOAuthError: When discovery or registration fails.
    """
    metadata = coros_oauth.discover_metadata()
    existing = coros_crud.get_integration(user_id, db)
    registration: coros_contracts.CorosClientRegistration | None = None
    if (
        existing is not None
        and existing.client_id
        and existing.issuer == metadata.issuer
        and existing.redirect_uri == redirect_uri
    ):
        registration = coros_contracts.CorosClientRegistration(
            client_id=existing.client_id,
            client_secret=existing.client_secret,
        )
    if registration is None:
        registration = coros_oauth.register_client(metadata, redirect_uri)

    state = coros_oauth.generate_state()
    verifier, challenge = coros_oauth.generate_pkce_pair()
    coros_crud.set_pending_authorization(
        user_id,
        metadata,
        registration,
        redirect_uri,
        state,
        verifier,
        datetime.now(UTC) + timedelta(minutes=coros_constants.STATE_TTL_MINUTES),
        db,
    )
    db.commit()
    logger.info(
        "COROS authorization started",
        extra=core_logger.context(user_id=user_id),
    )
    return coros_oauth.build_authorization_url(metadata, registration.client_id, redirect_uri, state, challenge)


def complete_link(user_id: int, code: str, state: str, db: Session) -> None:
    """Finish the OAuth round-trip and store the tokens.

    Args:
        user_id: Authenticated user.
        code: Authorization code.
        state: State echoed by COROS.
        db: Database session.

    Raises:
        core_exceptions.InvalidInputError: When the state is unknown, belongs to
            another user, or has expired.
        coros_oauth.CorosOAuthError: When the exchange fails.
    """
    pending = coros_crud.get_by_state(state, db)
    if pending is None or pending.user_id != user_id:
        raise core_exceptions.InvalidInputError("Invalid COROS authorization state")
    expires_at = core_timezone.to_utc_aware(pending.state_expires_at)
    if (
        not pending.code_verifier
        or not pending.client_id
        or not pending.redirect_uri
        or expires_at is None
        or expires_at <= datetime.now(UTC)
    ):
        coros_crud.clear_pending_authorization(user_id, db)
        db.commit()
        raise core_exceptions.InvalidInputError("COROS authorization state expired")

    metadata = _metadata_from_data(pending)
    registration = coros_contracts.CorosClientRegistration(
        client_id=pending.client_id,
        client_secret=pending.client_secret,
    )
    try:
        tokens = coros_oauth.exchange_code(
            metadata,
            registration,
            code,
            pending.redirect_uri,
            pending.code_verifier,
        )
    except coros_oauth.CorosAuthenticationError:
        # A rejected client means the next attempt must register a fresh one.
        coros_crud.clear_client_registration(user_id, db)
        coros_crud.clear_pending_authorization(user_id, db)
        db.commit()
        raise
    coros_crud.save_tokens(user_id, tokens, db)
    db.commit()
    logger.info("COROS account linked", extra=core_logger.context(user_id=user_id))


def get_status(user_id: int, db: Session) -> coros_schema.CorosStatusRead:
    """Return the caller's COROS status.

    Args:
        user_id: Authenticated user.
        db: Database session.

    Returns:
        The status; an unlinked view when the user never connected COROS.
    """
    status = coros_crud.get_status(user_id, db)
    return status or coros_schema.CorosStatusRead(linked=False)


def get_valid_connection(
    user_id: int,
    db: Session | None = None,
) -> coros_schema.CorosIntegrationData:
    """Return a connection with a usable access token, refreshing it if needed.

    Args:
        user_id: Owning user.
        db: Optional request session; a short one is opened when omitted.

    Returns:
        The connection with a fresh access token.

    Raises:
        coros_oauth.CorosAuthenticationError: When the user must reconnect.
        coros_oauth.CorosOAuthError: When the refresh fails.
    """
    session = db or core_database.SessionLocal()
    try:
        data = coros_crud.get_integration(user_id, session)
        if data is None or not data.access_token or not data.refresh_token:
            raise coros_oauth.CorosAuthenticationError("COROS is not connected")

        expires_at = core_timezone.to_utc_aware(data.token_expires_at)
        if expires_at is None or expires_at > datetime.now(UTC) + timedelta(
            minutes=coros_constants.TOKEN_REFRESH_SKEW_MINUTES
        ):
            return data

        refresh_expires_at = core_timezone.to_utc_aware(data.refresh_token_expires_at)
        if refresh_expires_at is not None and refresh_expires_at <= datetime.now(UTC):
            raise coros_oauth.CorosAuthenticationError("COROS refresh token expired")

        metadata = _metadata_from_data(data)
        registration = coros_contracts.CorosClientRegistration(
            client_id=data.client_id or "",
            client_secret=data.client_secret,
        )
        tokens = coros_oauth.refresh_tokens(metadata, registration, data.refresh_token)
        coros_crud.update_tokens(user_id, tokens, session)
        session.commit()
        refreshed = coros_crud.get_integration(user_id, session)
        if refreshed is None:
            raise coros_oauth.CorosAuthenticationError("COROS is not connected")
        logger.info("COROS tokens refreshed", extra=core_logger.context(user_id=user_id))
        return refreshed
    finally:
        if db is None:
            session.close()


def unlink(user_id: int, db: Session) -> None:
    """Revoke the stored tokens when possible and clear the connection.

    Args:
        user_id: Authenticated user.
        db: Database session.
    """
    data = coros_crud.get_integration(user_id, db)
    if data is None:
        coros_crud.clear_tokens(user_id, db)
        db.commit()
        return
    try:
        metadata = _metadata_from_data(data)
        registration = coros_contracts.CorosClientRegistration(
            client_id=data.client_id or "",
            client_secret=data.client_secret,
        )
        if data.refresh_token:
            coros_oauth.revoke_token(metadata, registration, data.refresh_token, "refresh_token")
        if data.access_token:
            coros_oauth.revoke_token(metadata, registration, data.access_token, "access_token")
    except coros_oauth.CorosOAuthError as err:
        logger.info(
            "COROS token revocation was not possible; unlinking locally",
            extra=core_logger.context(user_id=user_id),
        )
        logger.debug("COROS revocation failure", exc_info=err)
    coros_crud.clear_tokens(user_id, db)
    db.commit()
    logger.info("COROS account unlinked", extra=core_logger.context(user_id=user_id))


def mark_sync_success(user_id: int, activity_count: int) -> None:
    """Record a successful sync in a short session.

    Args:
        user_id: Owning user.
        activity_count: Activities stored by the sync.
    """
    with core_database.SessionLocal() as db:
        coros_crud.mark_sync_success(user_id, activity_count, db)
        db.commit()


def mark_sync_error(user_id: int, error_code: coros_constants.SyncErrorCode) -> None:
    """Record a failed sync in a short session.

    Args:
        user_id: Owning user.
        error_code: Sanitized failure code.
    """
    with core_database.SessionLocal() as db:
        coros_crud.mark_sync_error(user_id, error_code, db)
        db.commit()


def reserve_fit_download(user_id: int) -> bool:
    """Reserve one FIT download from the user's daily quota.

    Args:
        user_id: Owning user.

    Returns:
        True when the request may proceed.
    """
    with core_database.SessionLocal() as db:
        allowed = coros_crud.reserve_fit_download(user_id, db)
        db.commit()
        return allowed
