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

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import users.user_identity_providers.crud as user_idp_crud

import auth.identity_providers.crud as idp_crud
import auth.identity_providers.service as idp_service
import auth.idp_link_tokens.crud as idp_link_token_crud
import auth.oauth_state.crud as oauth_state_crud
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
    # Validate and retrieve link token
    db_token = idp_link_token_crud.get_idp_link_token_by_id(link_token, db)
    if not db_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired link token",
        )

    # Validate token matches the requested IdP
    if db_token.idp_id != idp_id:
        core_logger.print_to_log(
            f"Link token IdP mismatch: token idp_id={db_token.idp_id}, requested idp_id={idp_id}",
            "warning",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid link token for this identity provider",
        )

    # Optional: Validate IP address matches
    client_ip = request.client.host if request.client else None
    if db_token.ip_address and client_ip and db_token.ip_address != client_ip:
        core_logger.print_to_log(
            f"Link token IP mismatch: token ip={db_token.ip_address}, request ip={client_ip}",
            "warning",
        )
        # Note: This is a soft check - we log but don't fail (NAT, proxies, etc.)

    token_user_id = db_token.user_id
    # Validate IDP exists and is enabled
    idp = idp_crud.get_identity_provider(idp_id, db)
    if not idp or not idp.enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Identity provider not found or disabled",
        )

    # Check if already linked
    existing_link = user_idp_crud.get_user_identity_provider_by_user_id_and_idp_id(
        token_user_id, idp_id, db
    )
    if existing_link:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Identity provider {idp.name} is already linked to your account",
        )

    # Mark token as used to prevent replay attacks
    idp_link_token_crud.mark_token_as_used(link_token, db)

    # Create database-backed OAuth state for link mode
    state, nonce = oauth_state_utils.create_state_id_and_nonce()
    client_ip = request.client.host if request.client else None

    oauth_state_crud.create_oauth_state(
        db=db,
        state_id=state,
        idp_id=idp_id,
        nonce=nonce,
        client_type="web",  # Browser redirect = web client
        ip_address=client_ip,
        user_id=token_user_id,  # Indicates link mode
    )

    # Initiate OAuth flow in "link mode"
    try:
        authorization_url = await idp_service.idp_service.initiate_link(
            idp, request, token_user_id, db, oauth_state_id=state
        )

        # Audit logging
        core_logger.print_to_log(
            f"User {token_user_id} initiated IdP link: idp_id={idp_id} ({idp.name})"
        )

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
