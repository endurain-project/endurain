from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import users.user.schema as users_schema
import users.user.crud as users_crud
import users.user.utils as users_utils

import users.user_integrations.crud as user_integrations_crud

import users.user_privacy_settings.crud as users_privacy_settings_crud
import users.user_privacy_settings.schema as users_privacy_settings_schema

import profile.utils as profile_utils
import profile.schema as profile_schema
import profile.export_service as profile_export_service
import profile.import_service as profile_import_service
import profile.exceptions as profile_exceptions

import session.security as session_security
import session.crud as session_crud

import core.database as core_database
import core.logger as core_logger
import core.file_security.utils as core_file_security_utils

import websocket.schema as websocket_schema

# Define the API router
router = APIRouter()


@router.get("", response_model=users_schema.UserMe)
async def read_users_me(
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Retrieve the current authenticated user's profile, including integration and privacy settings.

    This endpoint extracts the user ID from the access token, fetches the user from the database,
    and enriches the user object with integration status (Strava, Garmin Connect) and privacy settings.
    Raises HTTP 401 errors if the user, user integrations, or privacy settings are not found.

    Args:
        token_user_id (int): The user ID extracted from the access token.
        db (Session): SQLAlchemy database session dependency.

    Returns:
        User: The user object with additional integration and privacy attributes.

    Raises:
        HTTPException: If the user, user integrations, or privacy settings are not found.
    """
    # Get the user from the database
    user = users_crud.get_user_by_id(token_user_id, db)

    # If the user does not exist raise the exception
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_integrations = user_integrations_crud.get_user_integrations_by_user_id(
        user.id, db
    )

    if user_integrations is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Could not validate credentials (user integrations not found)",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user.is_strava_linked = 1 if user_integrations.strava_token else 0
    user.is_garminconnect_linked = 1 if user_integrations.garminconnect_oauth1 else 0

    user_privacy_settings = (
        users_privacy_settings_crud.get_user_privacy_settings_by_user_id(user.id, db)
    )

    if user_privacy_settings is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Could not validate credentials (user privacy settings not found)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    else:
        for attr in vars(user_privacy_settings):
            if not attr.startswith("_") and attr != "id" and attr != "user_id":
                setattr(user, attr, getattr(user_privacy_settings, attr))

    # Return the user
    return user


@router.get("/sessions")
async def read_sessions_me(
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Retrieve all sessions associated with the currently authenticated user.

    Args:
        token_user_id (int): The ID of the user extracted from the access token.
        db (Session): The database session dependency.

    Returns:
        List[Session]: A list of session objects belonging to the authenticated user.
    """
    # Get the sessions from the database
    return session_crud.get_user_sessions(token_user_id, db)


@router.post(
    "/image",
    status_code=201,
    response_model=str | None,
)
async def upload_profile_image(
    file: UploadFile,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Handles the upload of a user's profile image with comprehensive security validation.

    Security features:
    - File type validation (JPEG, PNG, GIF, WebP only)
    - File size limits (max 20MB)
    - MIME type verification
    - Content-based file signature validation
    - Malicious file extension blocking

    Args:
        file (UploadFile): The image file to be uploaded.
        token_user_id (int): The ID of the user, extracted from the access token.
        db (Session): The database session dependency.

    Returns:
        The result of saving the user's image, as returned by `users_utils.save_user_image`.

    Raises:
        HTTPException: If the upload validation fails or save operation fails.
    """
    # Comprehensive security validation
    await core_file_security_utils.validate_profile_image_upload(file)

    # If validation passes, proceed with saving
    return await users_utils.save_user_image(token_user_id, file, db)


@router.put("")
async def edit_user(
    user_attributtes: users_schema.UserRead,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Edits the attributes of an existing user in the database.

    Args:
        user_attributtes (users_schema.UserRead): The updated user attributes to be saved.
        token_user_id (int): The ID of the user extracted from the access token.
        db (Session): The database session dependency.

    Returns:
        dict: A dictionary containing a success message with the updated user's ID.
    """
    # Update the user in the database
    users_crud.edit_user(token_user_id, user_attributtes, db)

    # Return success message
    return {"detail": f"User ID {user_attributtes.id} updated successfully"}


@router.put("/privacy")
async def edit_profile_privacy_settings(
    user_privacy_settings: users_privacy_settings_schema.UsersPrivacySettings,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Edits the privacy settings for the currently authenticated user.

    Args:
        user_privacy_settings (users_privacy_settings_schema.UsersPrivacySettings): The new privacy settings to apply to the user.
        token_user_id (int): The ID of the user extracted from the access token.
        db (Session): The database session dependency.

    Returns:
        dict: A message indicating that the user's privacy settings were updated successfully.
    """
    # Edit the user privacy settings in the database
    users_privacy_settings_crud.edit_user_privacy_settings(
        token_user_id, user_privacy_settings, db
    )

    # Return success message
    return {f"User ID {token_user_id} privacy settings updated successfully"}


@router.put("/password")
async def edit_profile_password(
    user_attributtes: users_schema.UserEditPassword,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Asynchronously updates the password for the authenticated user after validating password complexity.

    Args:
        user_attributtes (users_schema.UserEditPassword): The new password data provided by the user.
        token_user_id (int): The ID of the authenticated user, extracted from the access token.
        db (Session): The database session dependency.

    Raises:
        HTTPException: If the new password does not meet complexity requirements.

    Returns:
        dict: A success message indicating the user's password was updated.
    """
    # Check if the password meets the complexity requirements
    is_valid, message = session_security.is_password_complexity_valid(
        user_attributtes.password
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    # Update the user password in the database
    users_crud.edit_user_password(token_user_id, user_attributtes.password, db)

    # Return success message
    return {f"User ID {token_user_id} password updated successfully"}


@router.put("/photo")
async def delete_profile_photo(
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Deletes the profile photo of the authenticated user.

    Args:
        token_user_id (int): The ID of the user obtained from the access token.
        db (Session): The database session dependency.

    Returns:
        str: Success message indicating the user's photo was deleted.
    """
    # Update the user photo_path in the database
    users_crud.delete_user_photo(token_user_id, db)

    # Return success message
    return f"User ID {token_user_id} photo deleted successfully"


@router.delete("/sessions/{session_id}")
async def delete_profile_session(
    session_id: str,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Deletes a user session from the database.

    Args:
        session_id (str): The unique identifier of the session to be deleted.
        token_user_id (int): The ID of the user extracted from the access token.
        db (Session): The database session dependency.

    Returns:
        Any: The result of the session deletion operation, as returned by `session_crud.delete_session`.
    """
    # Delete the session from the database
    return session_crud.delete_session(session_id, token_user_id, db)


# Import/export logic


@router.get("/export")
async def export_profile_data(
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Exports all profile-related data for the authenticated user as a ZIP archive.

    This endpoint collects and packages the user's activities, associated files (such as GPX/FIT tracks),
    laps, sets, streams, workout steps, exercise titles, gears, health data, health targets, user information,
    user images, default gear, integrations, goals, and privacy settings into a single ZIP file.
    The resulting archive contains JSON files for structured data and includes any relevant user or activity files found on disk.

    Args:
        token_user_id (int): The ID of the authenticated user, extracted from the access token.
        db (Session): SQLAlchemy database session dependency.

    Returns:
        StreamingResponse: A streaming response containing the ZIP archive with all exported user data, suitable for download.

    Raises:
        HTTPException: If the user is not found in the database (404 Not Found).
    """
    # Get the user from the database
    user = users_crud.get_user_by_id(token_user_id, db)

    # If the user does not exist raise the exception
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Prepare user data (excluding password)
    user_dict = profile_utils.sqlalchemy_obj_to_dict(user)
    user_dict.pop("password", None)

    # Create export service and generate archive
    export_service = profile_export_service.ExportService(token_user_id, db)

    headers = {
        "Content-Disposition": f"attachment; filename=user_{token_user_id}_export.zip",
        # Content-Length is omitted for streaming
    }

    try:
        return StreamingResponse(
            export_service.generate_export_archive(user_dict),
            media_type="application/zip",
            headers=headers,
        )
    except (
        profile_exceptions.DatabaseConnectionError,
        profile_exceptions.FileSystemError,
        profile_exceptions.ZipCreationError,
        profile_exceptions.MemoryAllocationError,
        profile_exceptions.DataCollectionError,
        profile_exceptions.ExportTimeoutError,
    ) as err:
        # Handle specific export errors with appropriate HTTP responses
        http_exception = profile_exceptions.handle_import_export_exception(
            err, "profile data export"
        )
        core_logger.print_to_log(
            f"Export error for user {token_user_id}: {err}",
            "error",
            exc=err,
        )
        raise http_exception
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Unexpected error in export_profile_data for user {token_user_id}: {err}",
            "error",
            exc=err,
        )
        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


@router.post("/import")
async def import_profile_data(
    file: UploadFile,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    websocket_manager: Annotated[
        websocket_schema.WebSocketManager,
        Depends(websocket_schema.get_websocket_manager),
    ],
):
    """
    Import user profile data from a ZIP file with comprehensive security validation.

    This endpoint allows users to import their profile data from a previously exported ZIP file.
    The import process is performed asynchronously and handles various types of data including
    activities, settings, and other profile-related information.

    Security features:
    - File type validation (ZIP files only)
    - File size limits (max 500MB)
    - MIME type verification
    - Content-based file signature validation
    - Malicious file extension blocking

    Args:
        file (UploadFile): The uploaded ZIP file containing the profile data to import.
            Must have a .zip extension and pass security validation.
        token_user_id (int): The ID of the authenticated user performing the import.
            Extracted from the access token.
        db (Session): Database session dependency for performing database operations.
        websocket_manager (WebSocketManager): WebSocket manager for real-time updates
            during the import process.

    Returns:
        dict: A dictionary containing import results with information about what was imported,
            including counts of activities, settings, and other imported items.

    Raises:
        HTTPException(400): If the uploaded file fails security validation or if validation errors
            occur (e.g., file size limits, activity limits exceeded).
        HTTPException(507): If there is insufficient memory to process the import.
        HTTPException(500): If an unexpected internal error occurs during the import process.
        HTTPException: Various status codes may be raised by profile_exceptions.handle_import_export_exception for
            specific import/export errors (profile_exceptions.DatabaseConnectionError, profile_exceptions.FileSystemError,
            profile_exceptions.ZipCreationError, profile_exceptions.MemoryAllocationError, profile_exceptions.DataCollectionError, profile_exceptions.ExportTimeoutError).

    Example:
        The endpoint expects a multipart/form-data request with a ZIP file:
        ```
        POST /profile/import
        Content-Type: multipart/form-data
        Authorization: Bearer <token>
        file: profile_export.zip
        ```
    """
    # Comprehensive security validation
    await core_file_security_utils.validate_profile_data_upload(file)

    try:
        # Read the ZIP file data
        zip_data = await file.read()

        # Create import service and process the data
        import_service = profile_import_service.ImportService(
            token_user_id, db, websocket_manager
        )
        result = await import_service.import_from_zip_data(zip_data)

        core_logger.print_to_log(
            f"Successfully imported profile data for user {token_user_id}: {result['imported']}",
            "info",
        )

        return result

    except (
        profile_exceptions.ImportValidationError,
        profile_exceptions.FileFormatError,
        profile_exceptions.FileSizeError,
        profile_exceptions.ActivityLimitError,
        profile_exceptions.ZipStructureError,
        profile_exceptions.JSONParseError,
        profile_exceptions.SchemaValidationError,
    ) as err:
        # Handle import validation and format errors
        http_exception = profile_exceptions.handle_import_export_exception(
            err, "profile data import"
        )
        core_logger.print_to_log(
            f"Import validation error for user {token_user_id}: {err}",
            "warning",
        )
        raise http_exception
    except (
        profile_exceptions.DataIntegrityError,
        profile_exceptions.ImportTimeoutError,
        profile_exceptions.DiskSpaceError,
    ) as err:
        # Handle import operation errors
        http_exception = profile_exceptions.handle_import_export_exception(
            err, "profile data import"
        )
        core_logger.print_to_log(
            f"Import operation error for user {token_user_id}: {err}",
            "error",
            exc=err,
        )
        raise http_exception
    except ValueError as err:
        # Handle remaining validation errors for backward compatibility
        core_logger.print_to_log(
            f"Validation error in import_profile_data for user {token_user_id}: {err}",
            "warning",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err
    except (profile_exceptions.MemoryAllocationError, MemoryError) as err:
        # Handle memory-related errors
        http_exception = profile_exceptions.handle_import_export_exception(
            err, "profile data import"
        )
        core_logger.print_to_log(
            f"Memory error for user {token_user_id}: {err}",
            "error",
        )
        raise http_exception
    except (
        profile_exceptions.DatabaseConnectionError,
        profile_exceptions.FileSystemError,
        profile_exceptions.ZipCreationError,
        profile_exceptions.DataCollectionError,
        profile_exceptions.ExportTimeoutError,
    ) as err:
        # Handle specific import/export errors with appropriate HTTP responses
        http_exception = profile_exceptions.handle_import_export_exception(
            err, "profile data import"
        )
        core_logger.print_to_log(
            f"Import system error for user {token_user_id}: {err}",
            "error",
            exc=err,
        )
        raise http_exception
    except Exception as err:
        # Handle unexpected errors
        core_logger.print_to_log(
            f"Unexpected error in import_profile_data for user {token_user_id}: {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Import failed due to an internal error. Please try again or contact support.",
        ) from err


# MFA logic
@router.get("/mfa/status", response_model=profile_schema.MFAStatusResponse)
async def get_mfa_status(
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """
    Return the multi-factor authentication (MFA) enabled status for the authenticated user.

    This async route handler expects the authenticated user's ID to be injected from an access
    token and a database session to be provided via dependency injection. It checks whether the
    user has MFA enabled by delegating to profile_utils.is_mfa_enabled_for_user and returns the
    result wrapped in the profile_schema.MFAStatusResponse model.

    Args:
        token_user_id (int): User ID extracted from the access token (provided by
            session_security.get_user_id_from_access_token dependency).
        db (Session): SQLAlchemy database session (provided by core_database.get_db dependency).

    Returns:
        profile_schema.MFAStatusResponse: Response object with a single attribute:
            - mfa_enabled (bool): True if the user has MFA enabled, False otherwise.

    Raises:
        HTTPException: If authentication fails or the access token is invalid (raised by the
            dependency that extracts the user ID).
        sqlalchemy.exc.SQLAlchemyError: On database-related errors originating from the DB session
            or helper functions.

    Notes:
        - This function performs a read-only check and does not modify persistent state.
        - Intended to be used as a FastAPI route handler; the dependencies supply authentication
          and the DB session automatically.
        - Example serialized response: {"mfa_enabled": true}
    """
    is_enabled = profile_utils.is_mfa_enabled_for_user(token_user_id, db)
    return profile_schema.MFAStatusResponse(mfa_enabled=is_enabled)


@router.post("/mfa/setup", response_model=profile_schema.MFASetupResponse)
async def setup_mfa(
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    mfa_secret_store: Annotated[
        profile_schema.MFASecretStore, Depends(profile_schema.get_mfa_secret_store)
    ],
):
    """
    Initiate MFA setup for the authenticated user.

    Generates a new TOTP secret and associated provisioning data for the user identified
    by token_user_id, persists any required MFA metadata using the provided database
    session, and temporarily stores the raw secret in mfa_secret_store for the
    subsequent enable/verification step.

    Args:
        token_user_id (int): User ID extracted from the access token via
            session_security.get_user_id_from_access_token. The MFA setup will be
            performed for this user.
        db (Session): Database session (injected via core_database.get_db) used by
            profile_utils.setup_user_mfa to persist user MFA metadata.
        mfa_secret_store (profile_schema.MFASecretStore): Ephemeral secret store (injected
            via profile_schema.get_mfa_secret_store). The generated raw secret is added
            with mfa_secret_store.add_secret(token_user_id, secret) so it can be
            verified in a subsequent request that enables MFA.

    Returns:
        object: The response returned by profile_utils.setup_user_mfa. Typically this
        contains the information needed by the client to configure an authenticator
        app (for example: secret or masked secret, otpauth URI, and/or QR code data).

    Side effects:
        - Persists MFA-related metadata in the database via profile_utils.setup_user_mfa.
        - Temporarily stores the raw TOTP secret in mfa_secret_store; callers should
          ensure secrets are removed or expired after successful verification to avoid
          long-lived plaintext secrets.

    Errors/Exceptions:
        - Authentication/authorization errors if the access token is invalid or does not
          resolve to a user id (raised by the dependency).
        - Database-related errors from profile_utils.setup_user_mfa or the db session.
        - Storage errors from mfa_secret_store.add_secret (e.g., failure to persist the secret).
        Callers (API layer) should translate these into appropriate HTTP responses.

    Notes:
        - Intended to be used as a FastAPI endpoint where token_user_id and db are
          provided via Depends().
        - Ensure mfa_secret_store implements appropriate concurrency control and TTL/expiry
          for stored secrets.
    """
    response = profile_utils.setup_user_mfa(token_user_id, db)

    # Store the secret temporarily for the enable step
    mfa_secret_store.add_secret(token_user_id, response.secret)

    return response


@router.post("/mfa/enable")
async def enable_mfa(
    request: profile_schema.MFASetupRequest,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    mfa_secret_store: Annotated[
        profile_schema.MFASecretStore, Depends(profile_schema.get_mfa_secret_store)
    ],
):
    """
    Enable Multi-Factor Authentication (MFA) for the authenticated user.

    Completes an in-progress MFA setup by retrieving the temporary secret for the user,
    validating the provided one-time code (TOTP) and persisting the MFA configuration.
    The temporary secret is removed from the store on success or error to avoid leaking secrets.

    Parameters
    ----------
    request : profile_schema.MFASetupRequest
        Request body containing the MFA code (TOTP) submitted by the user.
    token_user_id : int
        ID of the authenticated user, injected from the access token dependency.
    db : Session
        Database session used to persist the user's MFA settings.
    mfa_secret_store : profile_schema.MFASecretStore
        Temporary storage used to retrieve and delete the user's MFA secret during setup.

    Returns
    -------
    dict
        JSON-serializable success message: {"message": "MFA enabled successfully"}.

    Raises
    ------
    HTTPException
        - 400 Bad Request if there is no MFA setup in progress (no temporary secret available).
        - Propagates HTTPException raised by the underlying validation/persistence (e.g., invalid TOTP,
          database errors). On any error the temporary secret is removed to ensure cleanup.

    Side effects
    ------------
    - Calls profile_utils.enable_user_mfa(...) to validate and enable MFA for the user.
    - Deletes the temporary MFA secret from mfa_secret_store in both success and error paths.
    """
    # Get the secret from temporary storage
    secret = mfa_secret_store.get_secret(token_user_id)
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No MFA setup in progress. Please run setup first.",
        )

    try:
        profile_utils.enable_user_mfa(token_user_id, secret, request.mfa_code, db)
        # Clean up the temporary secret
        mfa_secret_store.delete_secret(token_user_id)
        return {"message": "MFA enabled successfully"}
    except HTTPException:
        # Clean up on error
        mfa_secret_store.delete_secret(token_user_id)
        raise


@router.post("/mfa/disable")
async def disable_mfa(
    request: profile_schema.MFADisableRequest,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """Disable multi-factor authentication (MFA) for the authenticated user.

    Asynchronous FastAPI route handler that disables MFA for the user identified by
    the access token. It validates the MFA code provided in the request and delegates
    the disabling operation to profile_utils.disable_user_mfa, persisting the change
    using the supplied database session.

    Args:
        request (profile_schema.MFADisableRequest): Request payload containing the MFA code
            (expected attribute: `mfa_code`).
        token_user_id (int): ID of the authenticated user, resolved from the access token
            via dependency injection.
        db (Session): SQLAlchemy database session provided by dependency injection.

    Returns:
        dict: A JSON-serializable dict with a success message, e.g.:
            {"message": "MFA disabled successfully"}

    Raises:
        fastapi.HTTPException: If authentication fails or required dependencies cannot be resolved.
        ValueError: If the provided MFA code is invalid (actual exception type may vary
            depending on profile_utils implementation).
        sqlalchemy.exc.SQLAlchemyError: If a database error occurs while updating the user's record.
        Exception: Propagates other unexpected errors thrown by profile_utils.disable_user_mfa.

    Notes:
        - This function relies on FastAPI's Depends to supply token_user_id and db.
        - Side effects: updates the user's MFA state in the database.
    """
    profile_utils.disable_user_mfa(token_user_id, request.mfa_code, db)
    return {"message": "MFA disabled successfully"}


@router.post("/mfa/verify")
async def verify_mfa(
    request: profile_schema.MFARequest,
    token_user_id: Annotated[
        int,
        Depends(session_security.get_user_id_from_access_token),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
):
    is_valid = profile_utils.verify_user_mfa(token_user_id, request.mfa_code, db)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid MFA code"
        )
    return {"message": "MFA code verified successfully"}
