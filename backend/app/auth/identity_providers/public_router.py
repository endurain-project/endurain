from typing import Annotated, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import core.database as core_database
import core.rate_limit as core_rate_limit
import auth.password_hasher as auth_password_hasher
import auth.token_manager as auth_token_manager
import auth.utils as auth_utils
import session.utils as session_utils
import auth.identity_providers.crud as idp_crud
import auth.identity_providers.schema as idp_schema
import auth.identity_providers.service as idp_service
import users.user.schema as users_schema
import core.config as core_config
import core.logger as core_logger


# Define the API router
router = APIRouter()


@router.get(
    "",
    response_model=List[idp_schema.IdentityProviderPublic],
    status_code=status.HTTP_200_OK,
)
async def get_enabled_providers(db: Annotated[Session, Depends(core_database.get_db)]):
    """
    Retrieve a list of enabled identity providers from the database.

    Args:
        db (Session): SQLAlchemy database session dependency.

    Returns:
        List[IdentityProviderPublic]: A list of enabled identity providers, each represented as an IdentityProviderPublic schema.
    """
    providers = idp_crud.get_enabled_providers(db)
    return [
        idp_schema.IdentityProviderPublic(
            id=p.id,
            name=p.name,
            slug=p.slug,
            icon=p.icon,
        )
        for p in providers
    ]


@router.get("/login/{idp_slug}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
@core_rate_limit.limiter.limit(core_rate_limit.OAUTH_AUTHORIZE_LIMIT)
async def initiate_login(
    idp_slug: str,
    request: Request,
    db: Annotated[Session, Depends(core_database.get_db)],
):
    """
    Initiates the login process for a given identity provider using OAuth.

    Rate Limit: 10 requests per minute per IP
    Args:
        idp_slug (str): The slug identifier for the identity provider.
        request (Request): The incoming HTTP request object.
        db (Session): Database session dependency.
    Raises:
        HTTPException: If the identity provider is not found or is disabled.
    Returns:
        RedirectResponse: A redirect response to the identity provider's authorization URL.
    """
    # Get the identity provider
    idp = idp_crud.get_identity_provider_by_slug(idp_slug, db)
    if not idp or not idp.enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Identity provider not found or disabled",
        )

    # Initiate the OAuth flow
    authorization_url = await idp_service.idp_service.initiate_login(idp, request, db)

    return RedirectResponse(
        url=authorization_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )


@router.get("/callback/{idp_slug}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
@core_rate_limit.limiter.limit(core_rate_limit.OAUTH_CALLBACK_LIMIT)
async def handle_callback(
    request: Request,
    response: Response,
    idp_slug: str,
    password_hasher: Annotated[
        auth_password_hasher.PasswordHasher,
        Depends(auth_password_hasher.get_password_hasher),
    ],
    token_manager: Annotated[
        auth_token_manager.TokenManager,
        Depends(auth_token_manager.get_token_manager),
    ],
    db: Annotated[Session, Depends(core_database.get_db)],
    code: str = Query(..., description="Authorization code from IdP"),
    state: str = Query(..., description="State parameter for CSRF protection"),
):
    """
    Handle OAuth callback from an identity provider.
    This endpoint processes the OAuth authorization callback from external identity providers.
    It supports two modes: login mode (default) and link mode (for linking IdP to existing account).
    Args:
        idp_slug (str): The slug identifier of the identity provider.
        password_hasher (auth_password_hasher.PasswordHasher): Password hasher dependency for session management.
        token_manager (auth_token_manager.TokenManager): Token manager dependency for creating session tokens.
        db (Session): Database session dependency.
        code (str): Authorization code received from the identity provider.
        state (str): State parameter used for CSRF protection.
        request (Request | None): The incoming HTTP request. Defaults to None.
        response (Response | None): The HTTP response object. Defaults to None.
    Returns:
        RedirectResponse: A redirect response to either:
            - Settings page (link mode): /settings/security with success parameters
            - Login page (login mode): /login with session_id
            - Error page: /login with error parameter if callback fails
    Raises:
        HTTPException: If the identity provider is not found, disabled, or if callback processing fails.
    Notes:
        - In link mode: Redirects to settings without creating a new session
        - In login mode: Creates session tokens, stores session in database, sets authentication cookies
        - On error: Redirects to login page with error parameter
        - All redirects use HTTP 307 (Temporary Redirect) status code
    """
    try:
        # Get the identity provider
        idp = idp_crud.get_identity_provider_by_slug(idp_slug, db)
        if not idp or not idp.enabled:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Identity provider not found or disabled",
            )

        # Process the OAuth callback
        result = await idp_service.idp_service.handle_callback(
            idp, code, state, request, password_hasher, db
        )

        user = result["user"]
        is_link_mode = result.get("mode") == "link"

        # Handle link mode differently - redirect to settings without creating new session
        if is_link_mode:
            frontend_url = core_config.ENDURAIN_HOST
            redirect_url = (
                f"{frontend_url}/settings/security?idp_link=success&idp_name={idp.name}"
            )

            core_logger.print_to_log(
                f"IdP link successful for user {user.username}, IdP {idp.name}", "info"
            )

            return RedirectResponse(
                url=redirect_url,
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            )

        # LOGIN MODE: Create session and redirect to dashboard
        # Convert to UserRead schema
        user_read = users_schema.UserRead.model_validate(user)

        # Create session tokens
        (
            session_id,
            access_token_exp,
            access_token,
            refresh_token_exp,
            refresh_token,
            csrf_token,
        ) = auth_utils.create_tokens(user_read, token_manager)

        # Create the session and store it in the database
        session_utils.create_session(
            session_id, user_read, request, refresh_token, password_hasher, db
        )

        # Set authentication cookies
        response = auth_utils.create_response_with_tokens(
            response,
            access_token,
            refresh_token,
            csrf_token,
        )

        # Redirect to frontend
        frontend_url = core_config.ENDURAIN_HOST
        redirect_url = f"{frontend_url}/login?sso=success&session_id={session_id}"

        core_logger.print_to_log(
            f"SSO login successful for user {user.username} via {idp.name}", "info"
        )

        return RedirectResponse(
            url=redirect_url,
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers=response.headers,
        )

    except HTTPException:
        raise
    except Exception as err:
        core_logger.print_to_log(f"Error in SSO callback: {err}", "error", exc=err)

        # Redirect to frontend with error
        frontend_url = core_config.ENDURAIN_HOST
        error_url = f"{frontend_url}/login?error=sso_failed"

        return RedirectResponse(
            url=error_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )
