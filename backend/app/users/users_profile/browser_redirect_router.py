"""Browser redirect router for OAuth identity provider linking.

This module handles browser-based OAuth flows for linking
external identity providers to user accounts using one-time
link tokens.

Key Features:
- One-time link token validation
- OAuth state management
- Security checks (IP validation, token expiry)
- Browser redirect handling
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import auth.identity_providers.service as idp_service
import auth.identity_providers.utils as idp_utils
import auth.identity_service as auth_identity_service
import auth.oauth_state.utils as oauth_state_utils
import core.database as core_database
import core.logger as core_logger

# Define the API router
router = APIRouter()


@router.get(
    "/idp/{idp_id}/link",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    response_class=RedirectResponse,
)
async def link_identity_provider(
    idp_id: int,
    link_token: Annotated[str, Query(alias="link_token")],
    request: Request,
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
    identity_service: Annotated[
        auth_identity_service.IdentityService,
        Depends(auth_identity_service.get_identity_service),
    ],
    redirect: Annotated[
        str | None,
        Query(
            description="Frontend return path after linking (relative path or a configured custom scheme)",
        ),
    ] = None,
) -> RedirectResponse:
    """
    Initiate linking an identity provider using a one-time link token.

    This endpoint validates the one-time link token and initiates the OAuth flow
    to link an external identity provider (IdP) to the user's account. The user
    will be redirected to the IdP's authorization page.

    Security:
        - Uses one-time, short-lived (60s) link tokens instead of access tokens
        - Validates token expiry and single-use constraint
        - Optional IP address validation

    Args:
        idp_id (int): The ID of the identity provider to link.
        link_token (str): One-time link token from query parameter.
        request (Request): The FastAPI request object containing request context.
        db (Session): The database session for performing CRUD operations.

    Returns:
        RedirectResponse: A redirect to the identity provider's authorization URL
            with HTTP 307 status code.

    Raises:
        HTTPException:
            - 401 UNAUTHORIZED: If the link token is invalid, expired, or already used.
            - 404 NOT_FOUND: If the identity provider doesn't exist or is disabled.
            - 409 CONFLICT: If the identity provider is already linked to the user's account.
            - 500 INTERNAL_SERVER_ERROR: If an unexpected error occurs during the linking process.
    """
    # Validate the optional return path up front (open-redirect guard) so a bad
    # target fails before the one-time link token is consumed.
    idp_utils.validate_redirect_url(redirect)

    # Validate and claim the link token via auth facade.
    # This encapsulates all auth-owned CRUD calls (hash lookup, IP check,
    # existing-link check, atomic token claim) behind a single boundary.
    client_ip = request.client.host if request.client else None
    token_user_id = identity_service.validate_and_claim_browser_link_token(
        link_token=link_token,
        idp_id=idp_id,
        client_ip=client_ip,
    )

    # Validate IDP exists and is enabled (fetched via the auth service facade so
    # the router does not import the auth data layer directly).
    idp = idp_service.get_identity_provider(idp_id, db)
    if not idp or not idp.enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Identity provider not found or disabled",
        )

    # Create database-backed OAuth state for link mode
    state, nonce = oauth_state_utils.create_state_id_and_nonce()
    client_ip = request.client.host if request.client else None

    # A custom-scheme return target signals a native/mobile handoff (mirrors the
    # login flow); a plain relative path is a normal web return.
    client_type = "mobile" if idp_utils.is_custom_scheme_redirect(redirect) else "web"

    idp_service.create_link_oauth_state(
        db=db,
        state_id=state,
        idp_id=idp_id,
        nonce=nonce,
        client_type=client_type,
        ip_address=client_ip,
        user_id=token_user_id,  # Indicates link mode
        redirect_path=redirect,
    )

    # Initiate OAuth flow in "link mode"
    try:
        authorization_url = await idp_service.idp_service.initiate_link(
            idp, request, token_user_id, db, oauth_state_id=state
        )

        # Audit logging
        core_logger.print_to_log(f"User {token_user_id} initiated IdP link: idp_id={idp_id} ({idp.name})")

        return RedirectResponse(
            url=authorization_url,
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, private",
                "Pragma": "no-cache",
            },
        )

    except HTTPException:
        raise
    except Exception as err:
        core_logger.print_to_log(
            f"Error initiating IdP link for user {token_user_id}, idp_id={idp_id}: {err}",
            "error",
            exc=err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate identity provider linking",
        ) from err
