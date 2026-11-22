"""Application service for the COROS connection lifecycle and sync state."""

import uuid
from datetime import UTC, date, datetime, timedelta

import jasil.audit as jasil_audit
import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.database as core_database
import core.exceptions as core_exceptions
import core.logger as core_logger
import core.timezone as core_timezone
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.identity_providers.contracts as identity_providers_contracts
import modules.auth.schema as auth_schema
import modules.coros.audit_actions as coros_audit_actions
import modules.coros.constants as coros_constants
import modules.coros.contracts as coros_contracts
import modules.coros.crud as coros_crud
import modules.coros.oauth as coros_oauth
import modules.coros.schema as coros_schema

logger = core_logger.get_logger(__name__)


def _metadata_from_data(data: coros_contracts.CorosIntegrationData) -> coros_contracts.CorosOAuthMetadata:
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


def begin_authorization(user_id: uuid.UUID, redirect_uri: str, db: Session) -> str:
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
    try:
        metadata = coros_oauth.discover_metadata()
    except coros_oauth.CorosOAuthError as err:
        logger.debug(
            "Unable to discover the COROS OAuth metadata",
            exc_info=err,
            extra=core_logger.context(user_id=user_id),
        )
        raise core_exceptions.UpstreamError("Unable to connect to COROS") from err
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
        try:
            registration = coros_oauth.register_client(metadata, redirect_uri)
        except coros_oauth.CorosOAuthError as err:
            logger.debug(
                "Unable to register the COROS OAuth client",
                exc_info=err,
                extra=core_logger.context(user_id=user_id),
            )
            raise core_exceptions.UpstreamError("Unable to connect to COROS") from err

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


def complete_link(user_id: uuid.UUID, code: str, state: str, db: Session) -> None:
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
        _audit_link_failure(user_id, coros_audit_actions.LinkFailureReason.INVALID_STATE)
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
        _audit_link_failure(user_id, coros_audit_actions.LinkFailureReason.INVALID_STATE)
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
    except coros_oauth.CorosAuthenticationError as err:
        # A rejected client means the next attempt must register a fresh one.
        coros_crud.clear_client_registration(user_id, db)
        coros_crud.clear_pending_authorization(user_id, db)
        db.commit()
        _audit_link_failure(user_id, coros_audit_actions.LinkFailureReason.UPSTREAM)
        raise core_exceptions.UpstreamError("Unable to link the COROS account") from err
    except coros_oauth.CorosOAuthError as err:
        _audit_link_failure(user_id, coros_audit_actions.LinkFailureReason.UPSTREAM)
        raise core_exceptions.UpstreamError("Unable to link the COROS account") from err
    coros_crud.save_tokens(user_id, tokens, db)
    jasil_audit.stage(
        db,
        coros_audit_actions.ACCOUNT_LINK,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
    )
    db.commit()
    logger.info("COROS account linked", extra=core_logger.context(user_id=user_id))


def _audit_link_failure(user_id: uuid.UUID, reason: coros_audit_actions.LinkFailureReason) -> None:
    """Record a refused COROS link.

    Args:
        user_id: The user linking COROS.
        reason: Why the link was refused.
    """
    jasil_audit.record_detached(
        coros_audit_actions.ACCOUNT_LINK,
        outcome=jasil_audit.Outcome.FAILURE,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
        details=coros_audit_actions.LinkFailureDetails(reason=reason),
    )


def _request_range_sync(
    user_id: uuid.UUID,
    start_date: date,
    end_date: date,
    storage: platform_providers.StorageProvider,
    db: Session,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue one COROS range through the shared ingestion surface."""
    return activity_ingestion_integration.request_range_sync(
        coros_constants.PROVIDER_NAME,
        user_id,
        start_date,
        end_date,
        storage,
        db,
    )


def complete_link_and_queue_initial_sync(
    user_id: uuid.UUID,
    code: str,
    state: str,
    storage: platform_providers.StorageProvider,
    db: Session,
) -> None:
    """Finish the link, then queue the initial sync without failing a completed link.

    Args:
        user_id: The authenticated user.
        code: Authorization code returned by COROS.
        state: State echoed by COROS.
        storage: The platform storage provider.
        db: Database session.
    """
    complete_link(user_id, code, state, db)
    try:
        request_initial_sync(user_id, storage, db)
    except core_exceptions.DomainError as err:
        logger.warning(
            "COROS linked but the initial sync could not be queued",
            exc_info=err,
            extra=core_logger.context(user_id=user_id),
        )


def request_initial_sync(
    user_id: uuid.UUID,
    storage: platform_providers.StorageProvider,
    db: Session,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue the initial COROS sync of the last thirty days.

    Args:
        user_id: The authenticated user.
        storage: The platform storage provider.
        db: Database session.

    Returns:
        The accepted refresh job.
    """
    end_date = datetime.now(UTC).date()
    return _request_range_sync(
        user_id,
        end_date - timedelta(days=coros_constants.INITIAL_SYNC_DAYS - 1),
        end_date,
        storage,
        db,
    )


def request_sync(
    user_id: uuid.UUID,
    start_date: date | None,
    end_date: date | None,
    storage: platform_providers.StorageProvider,
    db: Session,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue a COROS sync, defaulting to the last seven days.

    Args:
        user_id: The authenticated user.
        start_date: First day of an explicit range, or ``None`` for the default window.
        end_date: Last day of an explicit range, or ``None`` for the default window.
        storage: The platform storage provider.
        db: Database session.

    Returns:
        The accepted refresh job.

    Raises:
        core_exceptions.InvalidInputError: When only one of the two dates is given.
    """
    if (start_date is None) != (end_date is None):
        raise core_exceptions.InvalidInputError("start_date and end_date must be provided together")
    if start_date is None or end_date is None:
        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=coros_constants.MANUAL_SYNC_DAYS - 1)
    if not get_status(user_id, db).linked:
        raise core_exceptions.ConflictError("COROS is not connected")
    return _request_range_sync(user_id, start_date, end_date, storage, db)


def get_status(user_id: uuid.UUID, db: Session) -> coros_schema.CorosStatusRead:
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
    user_id: uuid.UUID,
    *,
    db: Session | None = None,
) -> coros_contracts.CorosIntegrationData:
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


def unlink(
    user_id: uuid.UUID,
    step_up: auth_schema.StepUpVerification,
    verify_step_up: identity_providers_contracts.StepUpVerifier,
    db: Session,
) -> None:
    """Revoke the stored tokens when possible and clear the connection.

    Args:
        user_id: Authenticated user.
        step_up: The user's step-up verification.
        verify_step_up: Verifies the step-up for the calling user.
        db: Database session.

    Raises:
        StepUpFailedError: If the step-up does not verify.
    """
    verify_step_up(step_up, identity_providers_constants.StepUpAction.COROS_UNLINK)
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
    jasil_audit.stage(
        db,
        coros_audit_actions.ACCOUNT_UNLINK,
        target_type="user",
        target_id=str(user_id),
        target_owner_id=str(user_id),
    )
    db.commit()
    logger.info("COROS account unlinked", extra=core_logger.context(user_id=user_id))


def mark_sync_success(user_id: uuid.UUID, activity_count: int) -> None:
    """Record a successful sync in a short session.

    Args:
        user_id: Owning user.
        activity_count: Activities stored by the sync.
    """
    with core_database.SessionLocal() as db:
        coros_crud.mark_sync_success(user_id, activity_count, db)
        db.commit()
        logger.debug("COROS sync success recorded", extra=core_logger.context(user_id=user_id))


def mark_sync_error(user_id: uuid.UUID, error_code: coros_constants.SyncErrorCode) -> None:
    """Record a failed sync in a short session.

    Args:
        user_id: Owning user.
        error_code: Sanitized failure code.
    """
    with core_database.SessionLocal() as db:
        coros_crud.mark_sync_error(user_id, error_code, db)
        db.commit()
        logger.debug("COROS sync failure recorded", extra=core_logger.context(user_id=user_id))


def reserve_fit_download(user_id: uuid.UUID) -> bool:
    """Reserve one FIT download from the user's daily quota.

    Args:
        user_id: Owning user.

    Returns:
        True when the request may proceed.
    """
    with core_database.SessionLocal() as db:
        allowed = coros_crud.reserve_fit_download(user_id, db)
        db.commit()
        logger.debug("COROS FIT download quota checked", extra=core_logger.context(user_id=user_id))
        return allowed
