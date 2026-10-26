"""Strava account linking: the OAuth state and client, the code exchange and unlinking."""

import secrets
from datetime import UTC, date, datetime, timedelta

import jasil.providers as platform_providers
from sqlalchemy.orm import Session

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
import modules.users.users.integration_service as users_integration
import modules.users.users_integrations.integration_service as user_integrations_integration
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)


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
        InvalidInputError: When ``start_date`` is after ``end_date``, ``end_date`` is in the future or
            the range is longer than ``MAX_ACTIVITIES_RANGE_DAYS``.
    """
    if start_date > end_date:
        raise core_exceptions.InvalidInputError("start_date must not be after end_date")
    if end_date > users_integration.local_today(user_id, db):
        raise core_exceptions.InvalidInputError("end_date must not be in the future")
    if end_date - start_date >= timedelta(days=strava_constants.MAX_ACTIVITIES_RANGE_DAYS):
        raise core_exceptions.InvalidInputError(
            f"The date range must not exceed {strava_constants.MAX_ACTIVITIES_RANGE_DAYS} days"
        )

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
    user_integrations_integration.set_strava_client(
        user_id, str(credentials.client_id), credentials.client_secret.get_secret_value(), db
    )
    db.commit()
    logger.info("Strava client stored", extra=core_logger.context(user_id=user_id))


def begin_state(user_id: int, oauth_states: strava_oauth_state_store.StravaOAuthStateStore) -> str:
    """Issue the one-time state that correlates the OAuth callback with the user.

    Args:
        user_id: The authenticated user.
        oauth_states: The one-time OAuth state store.

    Returns:
        The opaque state, to be sent to Strava and handed back with the authorization code.
    """
    state = secrets.token_urlsafe(strava_constants.OAUTH_STATE_BYTES)
    oauth_states.begin(user_id, state)
    logger.debug("Strava state stored", extra=core_logger.context(user_id=user_id))
    return state


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
    locally anyway. The imported activities are deleted in batches, one transaction each, and
    the gear and the unlink then commit together last, so an interrupted unlink still finds the
    account linked and finishes when it runs again.

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

    deleted = _delete_imported_activities(user_id)
    with SessionLocal() as db:
        gears_integration.delete_all_strava_gear_for_user(user_id, db)
        user_integrations_integration.unlink_strava_account(user_id, db)
        db.commit()
    logger.info("Strava unlinked", extra=core_logger.context(user_id=user_id, deleted_activities=deleted))
    return True


def _delete_imported_activities(user_id: int) -> int:
    """Delete the activities imported from Strava, one batch per transaction.

    Args:
        user_id: The user to clear.

    Returns:
        The number of activities deleted.
    """
    total = 0
    while True:
        with SessionLocal() as db:
            deleted = activity_integration.delete_all_strava_activities(
                user_id, db, limit=strava_constants.UNLINK_DELETE_BATCH_SIZE
            )
            db.commit()
        total += deleted
        logger.debug(
            "Strava activities deleted in a batch", extra=core_logger.context(user_id=user_id, deleted=deleted)
        )
        if deleted < strava_constants.UNLINK_DELETE_BATCH_SIZE:
            return total
