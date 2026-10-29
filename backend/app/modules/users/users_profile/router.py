"""Profile API endpoints for user management and operations.

This module provides FastAPI endpoints for:
- User profile retrieval and updates
- Password and privacy settings management
- Profile photo upload and deletion
- Profile data export and import

The signed-in user's own sessions, two-step verification and identity provider links are
served under the same ``/profile`` prefix by the auth module (``modules.auth.sessions``,
``modules.auth.mfa`` and ``modules.auth.identity_providers``, each in a ``profile_router``).
"""

from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, Security, UploadFile, status
from fastapi.responses import StreamingResponse

import core.config as core_config
import core.dependencies as core_dependencies
import core.etag as core_etag
import core.file_uploads as core_file_uploads
import core.rate_limit as core_rate_limit
import modules.auth.authentication.dependencies as authentication_dependencies
import modules.auth.dependencies as auth_dependencies
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema
import modules.users.users_profile.dependencies as profile_dependencies
import modules.users.users_profile.export_job_service as profile_export_job_service
import modules.users.users_profile.import_job_service as profile_import_job_service
import modules.users.users_profile.schema as profile_schema
import modules.users.users_profile.service as profile_service

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=users_schema.UsersMe,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
def read_users_me(
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    response: Response,
) -> users_schema.UsersMe:
    """Retrieve authenticated user profile with integrations.

    The ETag is the user's version, which a later ``PATCH /profile`` echoes in ``If-Match``. The
    privacy settings have their own version, ``privacy_settings_version``.

    Args:
        token_user_id: User ID from access token.
        db: Database session.
        response: The response, which carries the user's ETag.

    Returns:
        User object with integration and privacy settings.
    """
    profile = profile_service.get_profile(token_user_id, db)
    core_etag.set_etag(response, profile.version)
    return profile


@router.post(
    "/photo",
    status_code=status.HTTP_201_CREATED,
    response_model=users_schema.UserPhotoRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def upload_profile_image(
    request: Request,
    file: UploadFile,
    token_user_id: auth_dependencies.CurrentUserId,
    storage: core_dependencies.Storage,
    db: core_dependencies.DbSession,
) -> users_schema.UserPhotoRead:
    """Upload user profile image with security validation.

    Args:
        request: The incoming request, read by the rate limiter.
        file: Image file to upload.
        token_user_id: User ID from access token.
        storage: The platform storage provider.
        db: Database session.

    Returns:
        The servable URL of the new photo.
    """
    users_integration.upload_user_photo(token_user_id, file, storage, db)
    return users_schema.UserPhotoRead(photo_path=users_integration.require_user(token_user_id, db).photo_path)


@router.patch(
    "",
    response_model=users_schema.UsersMe,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_user(
    request: Request,
    response: Response,
    user_attributtes: users_schema.ProfileUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    if_match: core_dependencies.IfMatch,
) -> users_schema.UsersMe:
    """Edit self-service profile fields for the authenticated user.

    Uses an explicit allow-list (:class:`users_schema.ProfileUpdate`)
    so administrative attributes such as ``access_type``,
    ``active``, ``mfa_enabled``, ``mfa_secret``, ``email_verified``,
    and ``pending_admin_approval`` cannot be modified through this
    endpoint, even if a malicious client submits them.

    Args:
        request: The incoming request, read by the rate limiter.
        response: The response, which carries the user's new ETag.
        user_attributtes: Allow-listed profile updates.
        token_user_id: User ID from access token.
        db: Database session.
        if_match: The ``If-Match`` precondition, the ``version`` the client read.

    Returns:
        The edited profile; its ``version`` is also sent as the ETag.
    """
    profile = profile_service.edit_profile(token_user_id, user_attributtes, db, if_match=if_match)
    core_etag.set_etag(response, profile.version)
    return profile


@router.post(
    "/email/change",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def edit_profile_email(
    request: Request,
    email_change: users_schema.EmailChange,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: Annotated[
        str,
        Depends(auth_dependencies.get_sid_from_access_token),
    ],
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> None:
    """Change the authenticated user's email after step-up verification.

    The address is where password resets go, so the caller must re-prove identity with the
    current password (and an MFA code when MFA is enabled). The new address starts unverified and
    a verification link is emailed to it.
    The user's other sessions are revoked when the request asks for it.

    Args:
        request: The incoming request, read by the rate limiter.
        email_change: The new address with the step-up credentials.
        token_user_id: User ID from access token.
        token_session_id: Session ID of the caller, preserved when other sessions are revoked.
        step_up_store: Step-up lockout store.
        db: Database session.
        db: Database session.
    """
    profile_service.change_email(token_user_id, email_change, token_session_id, step_up_store, db)


@router.patch(
    "/privacy",
    response_model=users_privacy_settings_schema.UsersPrivacySettingsRead,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_profile_privacy_settings(
    request: Request,
    response: Response,
    user_privacy_settings: users_privacy_settings_schema.UsersPrivacySettingsUpdate,
    token_user_id: auth_dependencies.CurrentUserId,
    db: core_dependencies.DbSession,
    if_match: core_dependencies.IfMatch,
) -> users_privacy_settings_schema.UsersPrivacySettingsRead:
    """Edit privacy settings for authenticated user.

    Args:
        request: The incoming request, read by the rate limiter.
        response: The response, which carries the settings' new ETag.
        user_privacy_settings: New privacy settings.
        token_user_id: User ID from access token.
        db: Database session.
        if_match: The ``If-Match`` precondition, the ``privacy_settings_version`` the client read.

    Returns:
        The edited settings; their ``version`` is also sent as the ETag.
    """
    updated = profile_service.edit_privacy_settings(token_user_id, user_privacy_settings, db, if_match=if_match)
    core_etag.set_etag(response, updated.version)
    return updated


@router.post(
    "/password/change",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def edit_profile_password(
    request: Request,
    user_attributtes: users_schema.UsersEditPassword,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: Annotated[
        str,
        Depends(auth_dependencies.get_sid_from_access_token),
    ],
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    db: core_dependencies.DbSession,
) -> None:
    """Update user password after step-up verification.

    Requires the caller to re-prove identity with the current
    password — and an MFA code when MFA is enabled — before the
    new password is accepted. This prevents a stolen access
    token alone from being parlayed into permanent account
    takeover.

    When ``revoke_other_sessions`` is set on the request, all of
    the user's other sessions are revoked after the change while
    the current session is preserved, so a password change can
    evict a suspected attacker without logging the caller out.

    Args:
        request: The incoming request, read by the rate limiter.
        user_attributtes: Schema with current password, new
            password, optional MFA code, and the optional
            ``revoke_other_sessions`` flag.
        token_user_id: ID of the user extracted from the access
            token.
        token_session_id: Session ID of the caller, preserved when
            other sessions are revoked.
        step_up_store: Step-up lockout store.
        db: Database session.

    Raises:
        HTTPException: 401 if step-up verification fails.
    """
    profile_service.change_password(token_user_id, user_attributtes, token_session_id, step_up_store, db)


@router.delete(
    "/photo",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_profile_photo(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    storage: core_dependencies.Storage,
    db: core_dependencies.DbSession,
) -> None:
    """Delete authenticated user's profile photo.

    Args:
        request: The incoming request, read by the rate limiter.
        token_user_id: User ID from access token.
        storage: The platform storage provider.
        db: Database session.
    """
    users_integration.delete_user_photo(token_user_id, storage, db)


# Import/export logic


@router.post(
    "/delete-account",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=users_schema.UserDeletionStatus,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def delete_my_account(
    request: Request,
    response: Response,
    step_up: users_schema.StepUpVerification,
    token_user_id: auth_dependencies.CurrentUserId,
    token_session_id: auth_dependencies.CurrentSessionId,
    step_up_store: Annotated[
        auth_dependencies.StepUpStore,
        Depends(auth_dependencies.get_step_up_attempts),
    ],
    state: core_dependencies.PlatformState,
    storage: core_dependencies.Storage,
    db: core_dependencies.DbSession,
) -> users_schema.UserDeletionStatus:
    """Queue the deletion of the authenticated user's account and all of their data.

    Requires step-up verification: the current password (or, for an account without one, a fresh
    identity-provider sign-in), and an MFA code when MFA is enabled. The
    account is signed out and deactivated at once and a background job erases the data, which is
    permanent and cannot be undone. Export the profile first to keep a copy. The browser's
    refresh-token cookie is cleared on the response.

    Args:
        request: The incoming request, read by the rate limiter.
        response: The response, which receives the cookie-deletion headers.
        step_up: Step-up verification payload.
        token_user_id: User ID from access token.
        token_session_id: Session ID from access token.
        step_up_store: Step-up lockout store.
        state: The platform state provider.
        storage: The platform storage provider.
        db: Database session.

    Returns:
        The deletion's initial status.
    """
    deletion = profile_service.delete_account(
        token_user_id, token_session_id, step_up, step_up_store, state, storage, db
    )
    authentication_dependencies.clear_refresh_token_cookies(response, environment=core_config.settings.ENVIRONMENT)
    return deletion


@router.post(
    "/export",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=profile_schema.ProfileExportStatus,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def export_profile_data(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    export_states: profile_dependencies.ProfileExportStateStoreDep,
    db: core_dependencies.DbSession,
) -> profile_schema.ProfileExportStatus:
    """Queue an export of all profile data as a ZIP archive.

    A worker builds the archive; poll ``GET /profile/export`` for the outcome and fetch it from
    ``GET /profile/export/download``.

    Args:
        request: The incoming request, read by the rate limiter.
        token_user_id: User ID from access token.
        export_states: Shared store of the export's state.
        db: Database session.

    Returns:
        The queued export's state.
    """
    state = profile_export_job_service.request_export(token_user_id, export_states, db)
    return profile_schema.ProfileExportStatus.model_validate(state)


@router.get(
    "/export",
    response_model=profile_schema.ProfileExportStatus,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
def read_profile_export_status(
    token_user_id: auth_dependencies.CurrentUserId,
    export_states: profile_dependencies.ProfileExportStateStoreDep,
) -> profile_schema.ProfileExportStatus:
    """Report where the authenticated user's profile export is.

    Args:
        token_user_id: User ID from access token.
        export_states: Shared store of the export's state.

    Returns:
        The export's state.
    """
    state = profile_export_job_service.get_export_status(token_user_id, export_states)
    return profile_schema.ProfileExportStatus.model_validate(state)


@router.get(
    "/export/download",
    response_class=StreamingResponse,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def download_profile_export(
    request: Request,
    token_user_id: auth_dependencies.CurrentUserId,
    export_states: profile_dependencies.ProfileExportStateStoreDep,
    storage: core_dependencies.Storage,
) -> StreamingResponse:
    """Download the authenticated user's finished profile export.

    Args:
        request: The incoming request, read by the rate limiter.
        token_user_id: User ID from access token.
        export_states: Shared store of the export's state.
        storage: The platform storage provider.

    Returns:
        Streaming response with the ZIP archive.
    """
    chunks, size = profile_export_job_service.open_export(token_user_id, export_states, storage)
    return StreamingResponse(
        chunks,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=user_{token_user_id}_export.zip",
            "Content-Length": str(size),
        },
    )


@router.post(
    "/import",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=profile_schema.ProfileImportStatus,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def import_profile_data(
    request: Request,
    file: UploadFile,
    token_user_id: auth_dependencies.CurrentUserId,
    import_states: profile_dependencies.ProfileImportStateStoreDep,
    storage: core_dependencies.Storage,
    db: core_dependencies.DbSession,
) -> profile_schema.ProfileImportStatus:
    """Queue a profile import from a ZIP archive.

    The archive is validated and staged, and a worker imports it; poll ``GET /profile/import`` for
    the outcome. The database part is all-or-nothing, so a failed import leaves nothing behind.

    Args:
        request: The incoming request, read by the rate limiter.
        file: ZIP file containing profile data.
        token_user_id: User ID from access token.
        import_states: Shared store of the import's state.
        storage: The platform storage provider.
        db: Database session.

    Returns:
        The queued import's state.
    """
    state = profile_import_job_service.request_import(
        token_user_id,
        partial(core_file_uploads.save_validated_upload_sync, file),
        import_states,
        storage,
        db,
    )
    return profile_schema.ProfileImportStatus.model_validate(state)


@router.get(
    "/import",
    response_model=profile_schema.ProfileImportStatus,
    dependencies=[Security(auth_dependencies.check_scopes, scopes=["profile"])],
)
def read_profile_import_status(
    token_user_id: auth_dependencies.CurrentUserId,
    import_states: profile_dependencies.ProfileImportStateStoreDep,
) -> profile_schema.ProfileImportStatus:
    """Report where the authenticated user's profile import is.

    Args:
        token_user_id: User ID from access token.
        import_states: Shared store of the import's state.

    Returns:
        The import's state.
    """
    state = profile_import_job_service.get_import_status(token_user_id, import_states)
    return profile_schema.ProfileImportStatus.model_validate(state)
