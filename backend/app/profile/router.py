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

from core.file_security.config import FileSecurityConfig, SecurityLimits
from core.file_security.file_validator import FileValidator
from core.file_security.exceptions import FileValidationError

import websocket.schema as websocket_schema

# Define the API router
router = APIRouter()

custom_limits = SecurityLimits(
    max_uncompressed_size=2 * 1024 * 1024 * 1024,
    max_number_files_same_type=2000,
)
custom_config = FileSecurityConfig()
custom_config.limits = custom_limits

# Initialize the file validator
file_validator = FileValidator(config=custom_config)


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
    Retrieve authenticated user profile with integrations.

    Args:
        token_user_id: User ID from access token.
        db: Database session.

    Returns:
        User object with integration and privacy settings.

    Raises:
        HTTPException: If user or settings not found.
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
    Retrieve all sessions for authenticated user.

    Args:
        token_user_id: User ID from access token.
        db: Database session.

    Returns:
        List of session objects for the user.
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
    Upload user profile image with security validation.

    Args:
        file: Image file to upload.
        token_user_id: User ID from access token.
        db: Database session.

    Returns:
        Result of save operation.

    Raises:
        HTTPException: If validation or save fails.
    """
    # Comprehensive security validation
    try:
        await file_validator.validate_image_file(file)
    except FileValidationError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
        ) from err

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
    Edit user attributes in database.

    Args:
        user_attributtes: Updated user attributes.
        token_user_id: User ID from access token.
        db: Database session.

    Returns:
        Success message with user ID.
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
    Edit privacy settings for authenticated user.

    Args:
        user_privacy_settings: New privacy settings.
        token_user_id: User ID from access token.
        db: Database session.

    Returns:
        Success message.
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
    Update user password after validation.

    Args:
        user_attributtes: New password data.
        token_user_id: User ID from access token.
        db: Database session.

    Returns:
        Success message.

    Raises:
        HTTPException: If password complexity invalid.
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
    Delete authenticated user's profile photo.

    Args:
        token_user_id: User ID from access token.
        db: Database session.

    Returns:
        Success message.
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
    Delete user session from database.

    Args:
        session_id: Session identifier to delete.
        token_user_id: User ID from access token.
        db: Database session.

    Returns:
        Result of deletion operation.
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
    Export all profile data as ZIP archive.

    Args:
        token_user_id: User ID from access token.
        db: Database session.

    Returns:
        Streaming response with ZIP archive.

    Raises:
        HTTPException: If user not found or export fails.
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
    Import profile data from ZIP with security validation.

    Args:
        file: ZIP file containing profile data.
        token_user_id: User ID from access token.
        db: Database session.
        websocket_manager: WebSocket manager for updates.

    Returns:
        Import results with counts of imported items.

    Raises:
        HTTPException: If validation or import fails.
    """
    # Comprehensive security validation
    try:
        await file_validator.validate_zip_file(file)
    except FileValidationError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
        ) from err

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
    Return MFA enabled status for authenticated user.

    Args:
        token_user_id: User ID from access token.
        db: Database session.

    Returns:
        MFA status response with enabled flag.
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
    Initiate MFA setup for authenticated user.

    Args:
        token_user_id: User ID from access token.
        db: Database session.
        mfa_secret_store: Temporary secret storage.

    Returns:
        MFA setup response with secret and QR code.
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
    Enable MFA for authenticated user.

    Args:
        request: MFA setup request with code.
        token_user_id: User ID from access token.
        db: Database session.
        mfa_secret_store: Temporary secret storage.

    Returns:
        Success message.

    Raises:
        HTTPException: If no setup in progress or invalid.
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
    """
    Disable MFA for authenticated user.

    Args:
        request: MFA disable request with code.
        token_user_id: User ID from access token.
        db: Database session.

    Returns:
        Success message.
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
    """
    Verify MFA code for authenticated user.

    Args:
        request: MFA request with code to verify.
        token_user_id: User ID from access token.
        db: Database session.

    Returns:
        Success message.

    Raises:
        HTTPException: If MFA code is invalid.
    """
    is_valid = profile_utils.verify_user_mfa(token_user_id, request.mfa_code, db)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid MFA code"
        )
    return {"message": "MFA code verified successfully"}
