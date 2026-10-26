"""Strava account linking: the OAuth state and client, the code exchange and unlinking."""

from datetime import UTC, date, datetime

import jasil.providers as platform_providers
from sqlalchemy.orm import Session
from stravalib.exc import AccessUnauthorized

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.gears.gear.integration_service as gears_integration
import modules.strava.client_service as strava_client_service
import modules.strava.constants as strava_constants
import modules.strava.schema as strava_schema
import modules.users.users_integrations.integration_service as user_integrations_integration

logger = core_logger.get_logger(__name__)


def link_account(state: str, code: str, user_id: int, db: Session) -> strava_schema.StravaDetail:
    """Exchange a Strava authorization code for tokens and store them.

    A failed exchange unlinks the account again, so a half-linked integration is
    never left behind.

    Args:
        state: The state the user stored before the OAuth round-trip.
        code: The authorization code Strava returned.
        user_id: The authenticated user.
        db: Database session.

    Returns:
        A success message.

    Raises:
        NotFoundError: When the state does not belong to the user.
        InvalidInputError: When the user has not stored a client ID and secret.
        DependencyFailedError: When the exchange with Strava fails.
    """
    user_integrations = user_integrations_integration.get_integrations_by_strava_state(state, db)

    # The state must belong to the authenticated user
    if user_integrations is None or user_integrations.user_id != user_id:
        raise core_exceptions.NotFoundError("User integrations not found")

    if user_integrations.strava_client_id is None and user_integrations.strava_client_secret is None:
        raise core_exceptions.InvalidInputError("Strava client ID and secret not set")

    try:
        strava_client = strava_client_service.create_strava_client(user_integrations)
        tokens = strava_client.exchange_code_for_token(
            client_id=core_cryptography.decrypt_token_fernet(user_integrations.strava_client_id),
            client_secret=core_cryptography.decrypt_token_fernet(user_integrations.strava_client_secret),
            code=code,
        )

        user_integrations_integration.link_strava_account(user_integrations.user_id, tokens, db)
        db.commit()
    except Exception as err:
        logger.error(
            "Unable to link Strava account", extra=core_logger.context(user_id=user_integrations.user_id), exc_info=err
        )

        db.rollback()
        user_integrations_integration.unlink_strava_account(user_integrations.user_id, db)
        db.commit()

        raise core_exceptions.DependencyFailedError(f"Unable to link Strava account: {err}") from err

    logger.info("Strava linked", extra=core_logger.context(user_id=user_integrations.user_id))
    return strava_schema.StravaDetail(detail=f"Strava linked successfully for user {user_integrations.user_id}")


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


def set_client(user_id: int, client_id: int | None, client_secret: str | None, db: Session) -> None:
    """Store the user's Strava API client id and secret.

    Args:
        user_id: The authenticated user.
        client_id: The Strava application's client id.
        client_secret: The Strava application's client secret.
        db: Database session.
    """
    user_integrations_integration.set_strava_client(user_id, client_id, client_secret, db)
    db.commit()
    logger.info("Strava client stored", extra=core_logger.context(user_id=user_id))


def set_state(user_id: int, state: str | None, db: Session) -> None:
    """Store the one-time state that correlates the OAuth callback with the user.

    Args:
        user_id: The authenticated user.
        state: The opaque state, or ``None`` to clear it.
        db: Database session.
    """
    user_integrations_integration.set_strava_state(user_id, state, db)
    db.commit()
    logger.info("Strava state stored", extra=core_logger.context(user_id=user_id))


def unlink_account(user_id: int, db: Session) -> None:
    """Disconnect the user's Strava account and delete what was imported from it.

    Strava is asked to revoke the authorization first; if it refuses, the
    account is unlinked locally anyway.

    Args:
        user_id: The authenticated user.
        db: Database session.
    """
    strava_client = strava_client_service.create_strava_client(
        strava_client_service.fetch_user_integrations_and_validate_token(user_id, db)
    )

    if strava_client:
        try:
            strava_client.deauthorize()
        except (AccessUnauthorized, Exception) as err:
            logger.info(
                "Unable to deauthorize Strava account, using stravalib deauthorize logic. Will unlink forcibly",
                exc_info=err,
            )

    gears_integration.delete_all_strava_gear_for_user(user_id, db)
    activity_integration.delete_all_strava_activities(user_id, db)

    # The commit covers the staged gear and activity deletions with the unlink
    user_integrations_integration.unlink_strava_account(user_id, db)
    db.commit()
    logger.info("Strava unlinked", extra=core_logger.context(user_id=user_id))
