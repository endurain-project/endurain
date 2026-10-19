import tempfile
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Annotated

import jasil.providers as platform_providers
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Security, UploadFile, status
from sqlalchemy.orm import Session
from stravalib.exc import AccessUnauthorized

import core.cryptography as core_cryptography
import core.database as core_database
import core.dependencies as core_dependencies
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.logger as core_logger
import core.rate_limit as core_rate_limit
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity_ingestion.integration_service as activity_ingestion_integration
import modules.activities.activity_ingestion.schema as activity_ingestion_schema
import modules.auth.dependencies as auth_dependencies
import modules.gears.gear.crud as gears_crud
import modules.strava.gear_utils as strava_gear_utils
import modules.strava.provider_registry as strava_provider_registry
import modules.strava.schema as strava_schema
import modules.strava.utils as strava_utils
import modules.users.users_integrations.crud as user_integrations_crud

logger = core_logger.get_logger(__name__)

# Define the API router
router = APIRouter()

# Largest gear CSV accepted: a gear list is a few hundred rows at most.
_GEAR_CSV_MAX_BYTES = 2 * 1024 * 1024


@router.put(
    "/link",
)
async def strava_link(
    state: str,
    code: str,
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_dependencies.validate_access_token),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get the user integrations by the state
    user_integrations = user_integrations_crud.get_user_integrations_by_strava_state(state, db)

    # The state must belong to the authenticated user
    if user_integrations is None or user_integrations.user_id != token_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User integrations not found",
        )

    # Check if client ID and client secret are set
    if user_integrations.strava_client_id is None and user_integrations.strava_client_secret is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Strava client ID and secret not set",
        )

    try:
        # Create a Strava client
        strava_client = strava_utils.create_strava_client(user_integrations)

        # Exchange code for token
        tokens = strava_client.exchange_code_for_token(
            client_id=core_cryptography.decrypt_token_fernet(user_integrations.strava_client_id),
            client_secret=core_cryptography.decrypt_token_fernet(user_integrations.strava_client_secret),
            code=code,
        )

        # Update the user integrations with the tokens
        user_integrations_crud.link_strava_account(user_integrations.user_id, tokens, db)

        # Return success message
        return {"detail": f"Strava linked successfully for user {user_integrations.user_id}"}
    except Exception as err:
        logger.error(f"Unable to link Strava account: {err}", exc_info=err)

        # Clean up by setting Strava
        user_integrations_crud.unlink_strava_account(user_integrations.user_id, db)

        # Raise an HTTPException with appropriate status code
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail=f"Unable to link Strava account: {err}",
        ) from err


@router.get(
    "/activities",
    status_code=202,
    response_model=activity_ingestion_schema.ActivityIngestionJobRead,
)
@core_rate_limit.limiter.limit(core_rate_limit.PROVIDER_SYNC)
def strava_retrieve_activities_days(
    request: Request,
    start_date: date,
    end_date: date,
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_dependencies.validate_access_token),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    storage: Annotated[
        platform_providers.StorageProvider,
        Depends(core_dependencies.get_storage),
    ],
) -> activity_ingestion_schema.ActivityIngestionJobRead:
    """Queue a Strava sync of an explicit date range.

    Returns ``202`` with a job handle; poll ``GET /activities/ingestion-jobs/{job_id}``
    for the outcome. The range is fetched by a background job, never on this
    request or an API worker thread.
    """
    if start_date > end_date:
        raise core_exceptions.InvalidInputError("start_date must not be after end_date")

    job = activity_ingestion_integration.request_provider_sync(
        token_user_id,
        strava_provider_registry.PROVIDER_NAME,
        datetime.combine(start_date, datetime.min.time(), tzinfo=UTC),
        datetime.combine(end_date, datetime.max.time(), tzinfo=UTC),
        storage,
        db,
    )
    logger.info(f"Strava activities queued for user {token_user_id}")
    return job


@router.get("/gear", status_code=201)
async def strava_retrieve_gear(
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_dependencies.validate_access_token),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    background_tasks: BackgroundTasks,
):
    # Process strava activities in the background
    background_tasks.add_task(
        strava_gear_utils.get_user_gear,
        token_user_id,
    )

    # Return success message and status code 202
    logger.info(f"Strava gear will be processed in the background for user {token_user_id}")
    return {"detail": f"Strava gear will be processed in the background for for {token_user_id}"}


def _save_gear_csv(file: UploadFile) -> tuple[tempfile.TemporaryDirectory, str]:
    """Stream an uploaded gear CSV to a private temp directory.

    Args:
        file: The uploaded CSV.

    Returns:
        The temp directory (the caller closes it) and the saved file's path.
    """
    work_dir = tempfile.TemporaryDirectory(prefix="strava-gear-")
    try:
        path = core_file_uploads.save_text_upload_sync(
            file, upload_dir=work_dir.name, filename="gear.csv", max_bytes=_GEAR_CSV_MAX_BYTES
        )
    except BaseException:
        work_dir.cleanup()
        raise
    return work_dir, path


@router.post("/import/bikes", status_code=201)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def import_bikes_from_strava_export(
    request: Request,
    file: UploadFile,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """Create the bikes listed in an uploaded Strava ``bikes.csv``."""
    work_dir, path = _save_gear_csv(file)
    try:
        bikes_dict = strava_gear_utils.iterate_over_bikes_csv(path)
        bikes = (
            strava_gear_utils.transform_csv_bike_gear_to_schema_gear(bikes_dict, token_user_id) if bikes_dict else []
        )
        if bikes:
            gears_crud.create_multiple_gears(bikes, token_user_id, db)
        logger.info("Bike import complete.", extra=core_logger.context(console=True))
    finally:
        work_dir.cleanup()


@router.post("/import/shoes", status_code=201)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def import_shoes_from_strava_export(
    request: Request,
    file: UploadFile,
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """Create the shoes listed in an uploaded Strava ``shoes.csv``."""
    work_dir, path = _save_gear_csv(file)
    try:
        shoes_list = strava_gear_utils.iterate_over_shoes_csv(path)
        shoes = (
            strava_gear_utils.transform_csv_shoe_gear_to_schema_gear(shoes_list, token_user_id, db)
            if shoes_list
            else []
        )
        if shoes:
            gears_crud.create_multiple_gears(shoes, token_user_id, db)
        logger.info("Shoe import complete.", extra=core_logger.context(console=True))
    finally:
        work_dir.cleanup()


@router.put("/client")
async def strava_set_user_client(
    client: strava_schema.StravaClient,
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_dependencies.validate_access_token),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    # Set the user Strava client
    user_integrations_crud.set_user_strava_client(token_user_id, client.client_id, client.client_secret, db)

    # Return success message
    return {f"Strava client for user {token_user_id} edited successfully"}


@router.put(
    "/state/{state}",
)
async def strava_set_user_unique_state(
    state: str | None,
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_dependencies.validate_access_token),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    # Set the user Strava state
    user_integrations_crud.set_user_strava_state(token_user_id, state, db)

    # Return success message
    return {f"Strava state for user {token_user_id} edited successfully"}


@router.delete("/unlink")
async def strava_unlink(
    _validate_access_token: Annotated[
        Callable,
        Depends(auth_dependencies.validate_access_token),
    ],
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["profile"]),
    ],
    token_user_id: Annotated[
        int,
        Depends(auth_dependencies.get_sub_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    # Get Strava client
    strava_client = strava_utils.create_strava_client(
        strava_utils.fetch_user_integrations_and_validate_token(token_user_id, db)
    )

    # Deauthorize the Strava client
    if strava_client:
        try:
            strava_client.deauthorize()
        except (AccessUnauthorized, Exception) as err:
            logger.info(
                "Unable to deauthorize Strava account, using stravalib deauthorize logic. Will unlink forcibly",
                exc_info=err,
            )

    # delete all strava gear for user
    gears_crud.delete_all_strava_gear_for_user(token_user_id, db)

    # delete all strava activities for user
    activity_integration.delete_all_strava_activities(token_user_id, db)

    # unlink strava account
    user_integrations_crud.unlink_strava_account(token_user_id, db)

    # Return success message
    return {"detail": f"Strava unlinked for user {token_user_id} successfully"}
