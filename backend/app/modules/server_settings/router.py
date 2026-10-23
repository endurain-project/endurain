"""Admin routes for server settings, the login photo and the test email."""

from collections.abc import Callable
from typing import Annotated

import jasil.providers as platform_providers
from fastapi import (
    APIRouter,
    Depends,
    Header,
    Request,
    Response,
    Security,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

import core.database as core_database
import core.dependencies as core_dependencies
import core.etag as core_etag
import core.exceptions as core_exceptions
import core.rate_limit as core_rate_limit
import modules.auth.dependencies as auth_dependencies
import modules.server_settings.schema as server_settings_schema
import modules.server_settings.service as server_settings_service
import modules.users.users.integration_service as users_integration

# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=server_settings_schema.ServerSettingsAdminRead,
    status_code=status.HTTP_200_OK,
)
def read_server_settings(
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:read"]),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    response: Response,
) -> server_settings_schema.ServerSettingsAdminRead:
    """Get current server settings.

    Requires admin authentication with server_settings:read scope.

    Args:
        db: Database session.
        response: The response, which carries the ETag.

    Returns:
        Current server settings configuration. The tile API key is never returned,
        only whether one is stored.
    """
    settings = server_settings_service.get_server_settings_for_admin(db)
    # The tag the client echoes back in If-Match when it later saves.
    response.headers["ETag"] = core_etag.format_etag(settings.version)
    return settings


@router.put(
    "",
    response_model=server_settings_schema.ServerSettingsAdminRead,
    status_code=status.HTTP_200_OK,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_server_settings(
    request: Request,
    server_settings_attributes: server_settings_schema.ServerSettingsEdit,
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:write"]),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    response: Response,
    if_match: Annotated[str | None, Header(alias=core_etag.IF_MATCH_HEADER)] = None,
) -> server_settings_schema.ServerSettingsAdminRead:
    """Update server settings.

    Requires admin authentication with server_settings:write scope. The body replaces
    the whole configuration; only the API keys may be omitted, which keeps the stored
    ones. Send ``If-Match`` with the ETag from the read to make the write conditional;
    a stale tag is refused with 412 rather than reverting an admin who saved in between.

    Args:
        request: The HTTP request object.
        server_settings_attributes: Settings to update.
        db: Database session.
        response: The response, which carries the new ETag.
        if_match: The ``If-Match`` precondition, or None.

    Returns:
        Updated server settings configuration, without the tile API key.
    """
    updated = server_settings_service.edit_server_settings(server_settings_attributes, db, if_match=if_match)
    # This process applies the new CSP tile domains at once; the other processes poll for them.
    request.app.state.allowed_tile_domains = server_settings_service.allowed_tile_domains_for_url(
        updated.tileserver_url
    )
    response.headers["ETag"] = core_etag.format_etag(updated.version)
    return updated


@router.post(
    "/login-photo",
    response_model=dict[str, str],
    status_code=status.HTTP_201_CREATED,
)
@core_rate_limit.limiter.limit(core_rate_limit.UPLOAD)
def upload_login_photo(
    request: Request,
    file: UploadFile,
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:write"]),
    ],
    storage: Annotated[
        platform_providers.StorageProvider,
        Depends(core_dependencies.get_storage),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> dict[str, str]:
    """Upload custom login page photo.

    Requires admin authentication with server_settings:write scope.

    Args:
        request: The HTTP request object.
        file: Image file to upload.
        storage: The platform storage provider.
        db: Database session.

    Returns:
        A confirmation message.
    """
    server_settings_service.upload_login_photo(file, storage, db)

    return {"message": "Login photo uploaded successfully."}


@router.delete(
    "/login-photo",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def delete_login_photo(
    request: Request,
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:write"]),
    ],
    storage: Annotated[
        platform_providers.StorageProvider,
        Depends(core_dependencies.get_storage),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> None:
    """Delete custom login page photo.

    Requires admin authentication with server_settings:write scope.

    Args:
        request: The HTTP request object.
        storage: The platform storage provider.
        db: Database session.
    """
    server_settings_service.delete_login_photo(storage, db)


@router.get(
    "/email",
    response_model=server_settings_schema.EmailStatus,
    status_code=status.HTTP_200_OK,
)
def read_email_status(
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:read"]),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> server_settings_schema.EmailStatus:
    """Get whether outgoing email is usable.

    Requires admin authentication with server_settings:read scope.

    Args:
        db: Database session.

    Returns:
        Whether email is configured and, when not, the reasons (setting names only).
    """
    return server_settings_service.get_email_status(db)


@router.get(
    "/email/settings",
    response_model=server_settings_schema.MailSettingsAdminRead,
    status_code=status.HTTP_200_OK,
)
def read_mail_settings(
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:read"]),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    response: Response,
) -> server_settings_schema.MailSettingsAdminRead:
    """Get the mail server settings.

    Requires admin authentication with server_settings:read scope.

    Args:
        db: Database session.
        response: The response, which carries the ETag.

    Returns:
        The mail settings. The password is never returned, only whether one is stored;
        ``env_managed`` names the fields an environment variable currently sets.
    """
    mail_settings = server_settings_service.get_mail_settings_for_admin(db)
    response.headers["ETag"] = core_etag.format_etag(mail_settings.version)
    return mail_settings


@router.put(
    "/email/settings",
    response_model=server_settings_schema.MailSettingsAdminRead,
    status_code=status.HTTP_200_OK,
)
@core_rate_limit.limiter.limit(core_rate_limit.WRITE)
def edit_mail_settings(
    request: Request,
    mail_settings_attributes: server_settings_schema.MailSettingsEdit,
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:write"]),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    response: Response,
    if_match: Annotated[str | None, Header(alias=core_etag.IF_MATCH_HEADER)] = None,
) -> server_settings_schema.MailSettingsAdminRead:
    """Update the mail server settings.

    Requires admin authentication with server_settings:write scope. The body replaces
    the whole configuration; only the password may be omitted, which keeps the stored one.
    Send ``If-Match`` with the ETag from the read to make the write conditional; a stale
    tag is refused with 412.

    Args:
        request: The HTTP request object.
        mail_settings_attributes: Settings to update.
        db: Database session.
        response: The response, which carries the new ETag.
        if_match: The ``If-Match`` precondition, or None.

    Returns:
        Updated mail settings, without the password.

    Raises:
        InvalidInputError: 400 if the configuration is not usable.
        ConflictError: 409 if a field is set by an environment variable.
        PreconditionFailedError: 412 if the settings changed since the client read them.
    """
    updated = server_settings_service.edit_mail_settings(mail_settings_attributes, db, if_match=if_match)
    response.headers["ETag"] = core_etag.format_etag(updated.version)
    return updated


@router.post(
    "/email/test",
    response_model=dict[str, str],
    status_code=status.HTTP_200_OK,
)
@core_rate_limit.limiter.limit(core_rate_limit.SENSITIVE)
def send_test_email(
    request: Request,
    _check_scopes: Annotated[
        Callable,
        Security(auth_dependencies.check_scopes, scopes=["server_settings:write"]),
    ],
    token_user_id: Annotated[int, Depends(auth_dependencies.get_sub_from_access_token)],
    mail: Annotated[
        platform_providers.MailProvider,
        Depends(core_dependencies.get_mail),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
) -> dict[str, str]:
    """Send a test email to the requesting admin.

    Requires admin authentication with server_settings:write scope. The recipient
    is always the caller's own email address.

    Args:
        request: The HTTP request object.
        token_user_id: The requesting admin's user ID, from the access token.
        mail: The platform mail provider.
        db: Database session.

    Returns:
        A confirmation message naming the recipient address.

    Raises:
        ServiceUnavailableError: 503 if email is not configured.
        UpstreamError: 502 if the mail server did not accept the message.
    """
    admin = users_integration.get_user(token_user_id, db)
    if admin is None:
        raise core_exceptions.NotFoundError("User not found")
    server_settings_service.send_test_email(admin, mail, db)
    return {"message": f"Test email sent to {admin.email}."}
