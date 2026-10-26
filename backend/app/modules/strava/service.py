"""Strava account linking: the OAuth state and client, the code exchange and unlinking."""

from datetime import UTC, date, datetime

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.gears.gear.integration_service as gears_integration
import modules.strava.client_service as strava_client_service
import modules.strava.constants as strava_constants
import modules.strava.oauth_state_store as strava_oauth_state_store
import modules.strava.schema as strava_schema
import modules.users.users_integrations.integration_service as user_integrations_integration
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)


def link_account(
    link: strava_schema.StravaLinkRequest,
    user_id: int,
    oauth_states: strava_oauth_state_store.StravaOAuthStateStore,
    db: Session,
) -> strava_schema.StravaDetail:
    """Exchange a Strava authorization code for tokens and store them.

    The state is consumed first, so a callback is accepted once and only for the
    user who stored it. The stored client credentials survive a failed exchange, so
    the user can retry without entering them again. The exchange is one bounded
    Strava call made with no database session open.

    Args:
        link: The state and authorization code Strava returned.
        user_id: The authenticated user.
        oauth_states: The one-time OAuth state store.
        db: Database session.

    Returns:
        A success message.

    Raises:
        InvalidInputError: When the state is unknown or expired, or the user has not stored a client ID and secret.
        DependencyFailedError: When the exchange with Strava fails.
    """
    if not oauth_states.consume(user_id, link.state):
        logger.warning("Strava link refused: unknown or expired state", extra=core_logger.context(user_id=user_id))
        raise core_exceptions.InvalidInputError("The Strava link state is invalid or has expired")

    with SessionLocal() as read_db:
        user_integrations = user_integrations_integration.get_user_integrations(user_id, read_db)

    if (
        user_integrations is None
        or user_integrations.strava_client_id is None
        or user_integrations.strava_client_secret is None
    ):
        raise core_exceptions.InvalidInputError("Strava client ID and secret not set")

    try:
        tokens = strava_client_service.create_strava_client(user_integrations).exchange_code_for_token(
            client_id=core_cryptography.decrypt_token_fernet(user_integrations.strava_client_id),
            client_secret=core_cryptography.decrypt_token_fernet(user_integrations.strava_client_secret),
            code=link.code,
        )
    except Exception as err:
        logger.error("Unable to link Strava account", extra=core_logger.context(user_id=user_id), exc_info=err)
        raise core_exceptions.DependencyFailedError("Unable to link Strava account") from err

    user_integrations_integration.link_strava_account(user_id, tokens, db)
    db.commit()

    logger.info("Strava linked", extra=core_logger.context(user_id=user_id))
    return strava_schema.StravaDetail(detail=f"Strava linked successfully for user {user_id}")


def request_activities_sync(
    user_id: int,
    start_date: date,
    end_date: date,
    storage: platform_providers.StorageProvider,
    db: Session,
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue a Strava sync of an explicit date range.

    The range is fetched by a background job, never on the request or an API
    worker thread.

    Args:
        user_id: The authenticated user.
        start_date: First day of the range.
        end_date: Last day of the range, inclusive.
        storage: The blob-storage provider.
        db: Database session.

    Returns:
        The accepted refresh job, whose outcome is polled on the ingestion-jobs route.

    Raises:
        InvalidInputError: When ``start_date`` is after ``end_date``.
    """
    if start_date > end_date:
        raise core_exceptions.InvalidInputError("start_date must not be after end_date")

    job = activity_ingestion_integration.request_provider_sync(
        user_id,
        strava_constants.PROVIDER_NAME,
        datetime.combine(start_date, datetime.min.time(), tzinfo=UTC),
        datetime.combine(end_date, datetime.max.time(), tzinfo=UTC),
        storage,
        db,
    )
    logger.info("Strava activities queued", extra=core_logger.context(user_id=user_id))
    return job


def set_client(user_id: int, credentials: strava_schema.StravaClientCredentials, db: Session) -> None:
    """Store the user's Strava API client id and secret.

    Args:
        user_id: The authenticated user.
        credentials: The Strava application's client id and secret.
        db: Database session.
    """
    user_integrations_integration.set_strava_client(user_id, str(credentials.client_id), credentials.client_secret, db)
    db.commit()
    logger.info("Strava client stored", extra=core_logger.context(user_id=user_id))


def set_state(user_id: int, state: str, oauth_states: strava_oauth_state_store.StravaOAuthStateStore) -> None:
    """Store the one-time state that correlates the OAuth callback with the user.

    Args:
        user_id: The authenticated user.
        state: The opaque state.
        oauth_states: The one-time OAuth state store.
    """
    oauth_states.begin(user_id, state)
    logger.debug("Strava state stored", extra=core_logger.context(user_id=user_id))


def clear_state(user_id: int, oauth_states: strava_oauth_state_store.StravaOAuthStateStore) -> None:
    """Forget the user's pending OAuth state.

    Args:
        user_id: The authenticated user.
        oauth_states: The one-time OAuth state store.
    """
    oauth_states.clear(user_id)
    logger.debug("Strava state cleared", extra=core_logger.context(user_id=user_id))


def unlink_account(user_id: int) -> bool:
    """Disconnect the user's Strava account and delete what was imported from it.

    Runs on a worker, never a request. Strava is asked to revoke the authorization
    first, with no database session open; if it refuses, the account is unlinked
    locally anyway. The deletions and the unlink then commit together.

    Args:
        user_id: The user to unlink.

    Returns:
        True once unlinked, False when Strava was not linked.

    Raises:
        NotFoundError: When the user has no integrations row.
    """
    with SessionLocal() as db:
        user_integrations = strava_client_service.fetch_user_integrations_and_validate_token(user_id, db)

    if user_integrations is None:
        logger.info("Strava not linked, nothing to unlink", extra=core_logger.context(user_id=user_id))
        return False

    try:
        strava_client_service.create_strava_client(user_integrations).deauthorize()
    except Exception as err:
        logger.warning(
            "Strava refused the deauthorization, unlinking locally anyway",
            extra=core_logger.context(user_id=user_id),
            exc_info=err,
        )

    with SessionLocal() as db:
        gears_integration.delete_all_strava_gear_for_user(user_id, db)
        activity_integration.delete_all_strava_activities(user_id, db)
        user_integrations_integration.unlink_strava_account(user_id, db)
        db.commit()
    logger.info("Strava unlinked", extra=core_logger.context(user_id=user_id))
    return True
