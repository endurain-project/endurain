"""Strava account linking: the OAuth state and client, the code exchange and unlinking."""

import secrets

from sqlalchemy.orm import Session

import core.database as core_database
import core.etag as core_etag
import core.logger as core_logger
import modules.activities.activity.integration_service as activity_integration
import modules.gears.gear.integration_service as gears_integration
import modules.strava.client_service as strava_client_service
import modules.strava.constants as strava_constants
import modules.strava.oauth_state_store as strava_oauth_state_store
import modules.strava.schema as strava_schema
import modules.users.users_integrations.integration_service as user_integrations_integration

logger = core_logger.get_logger(__name__)


def set_client(user_id: int, credentials: strava_schema.StravaClientCredentials, db: Session, *, if_match: str) -> int:
    """Store the user's Strava API client id and secret, and commit.

    Args:
        user_id: The authenticated user.
        credentials: The Strava application's client id and secret.
        db: Database session.
        if_match: The ``If-Match`` precondition.

    Returns:
        The integrations' new version, which a later write echoes in ``If-Match``.

    Raises:
        NotFoundError: If the user has no integrations.
        PreconditionFailedError: If the integrations changed since the client read them.
    """
    with core_etag.refuse_stale_write(
        db,
        "Strava client",
        lambda: user_integrations_integration.get_user_integrations(user_id, db) is not None,
        "User integrations not found",
    ):
        user_integrations_integration.set_strava_client(
            user_id, str(credentials.client_id), credentials.client_secret.get_secret_value(), db, if_match=if_match
        )
        db.commit()
    logger.info("Strava client stored", extra=core_logger.context(user_id=user_id))
    integrations = user_integrations_integration.get_user_integrations(user_id, db)
    return integrations.version if integrations is not None else 1


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
    with core_database.SessionLocal() as db:
        user_integrations = strava_client_service.fetch_user_integrations_and_validate_token(user_id, db)

    if user_integrations is None:
        logger.debug("Strava not linked, nothing to unlink", extra=core_logger.context(user_id=user_id))
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
    with core_database.SessionLocal() as db:
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
        with core_database.SessionLocal() as db:
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


def linked_user_ids(after_id: int, limit: int) -> list[int]:
    """Page through the users who have linked Strava, in a short session of its own.

    Args:
        after_id: Return only users with an id greater than this.
        limit: Maximum number of user ids to return.

    Returns:
        The linked user ids, ascending.
    """
    with core_database.SessionLocal() as db:
        return user_integrations_integration.list_user_ids_with_strava_linked(after_id, limit, db)
