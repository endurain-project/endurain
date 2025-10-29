from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

import users.user_identity_providers.crud as user_idp_crud

import auth.identity_providers.crud as idp_crud
import auth.identity_providers.service as idp_service

import auth.security as auth_security

import core.database as core_database
import core.logger as core_logger

# Define the API router
router = APIRouter()


@router.get(
    "/idp/{idp_id}/link",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
)
async def link_identity_provider(
    idp_id: int,
    request: Request,
    token_user_id: Annotated[
        int,
        Depends(auth_security.get_sub_from_access_token_for_browser_redirect),
    ],
    db: Annotated[
        Session,
        Depends(core_database.get_db),
    ],
):
    """
    Initiate linking an identity provider to the authenticated user's account.
    This endpoint starts the OAuth flow to link an external identity provider (IdP)
    to the currently authenticated user. The user will be redirected to the IdP's
    authorization page to complete the linking process.
    Args:
        idp_id (int): The ID of the identity provider to link.
        request (Request): The FastAPI request object containing request context.
        token_user_id (int): The authenticated user's ID extracted from the access token.
        db (Session): The database session for performing CRUD operations.
    Returns:
        RedirectResponse: A redirect to the identity provider's authorization URL
            with HTTP 307 status code.
    Raises:
        HTTPException:
            - 404 NOT_FOUND: If the identity provider doesn't exist or is disabled.
            - 409 CONFLICT: If the identity provider is already linked to the user's account.
            - 500 INTERNAL_SERVER_ERROR: If an unexpected error occurs during the linking process.
    Notes:
        - The function validates that the IdP exists and is enabled before proceeding.
        - Checks for existing links to prevent duplicate associations.
        - Logs the linking initiation for audit purposes.
        - Any errors during the OAuth flow initiation are logged and re-raised as HTTP exceptions.
    """
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

    # Initiate OAuth flow in "link mode"
    try:
        authorization_url = await idp_service.idp_service.initiate_link(
            idp, request, token_user_id, db
        )

        # Audit logging
        core_logger.print_to_log(
            f"User {token_user_id} initiated IdP link: idp_id={idp_id} ({idp.name})"
        )

        return RedirectResponse(
            url=authorization_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
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
