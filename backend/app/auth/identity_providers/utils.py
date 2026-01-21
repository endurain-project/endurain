"""Identity Provider utility functions and templates"""

import re
import hashlib
import base64
from typing import Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import auth.identity_providers.schema as idp_schema
import auth.identity_providers.service as idp_service

import users.users_identity_providers.crud as user_idp_crud

import core.logger as core_logger


def validate_pkce_challenge(code_challenge: str, code_challenge_method: str) -> None:
    """
    Validate PKCE code_challenge format according to RFC 7636.

    This function enforces RFC 7636 compliance for PKCE code challenges,
    ensuring that mobile clients provide properly formatted S256 challenges.

    Args:
        code_challenge (str): Base64url-encoded SHA256 hash of code verifier.
        code_challenge_method (str): PKCE method identifier (must be "S256").

    Raises:
        HTTPException: 400 Bad Request if validation fails (method not S256,
            length out of range, or invalid base64url characters).
    """
    # Only S256 is supported (SHA256)
    if code_challenge_method != "S256":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only S256 PKCE method is supported",
        )

    # RFC 7636: code_challenge length must be 43-128 characters (base64url)
    if not (43 <= len(code_challenge) <= 128):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code_challenge must be 43-128 characters",
        )

    # Validate base64url format (alphanumeric, dash, underscore only)
    if not re.match(r"^[A-Za-z0-9_-]+$", code_challenge):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code_challenge must be valid base64url",
        )


def validate_pkce_verifier(
    code_verifier: str, code_challenge: str, code_challenge_method: str
) -> None:
    """
    Validate PKCE code_verifier and verify it matches the code_challenge.

    This function implements RFC 7636 PKCE verification by computing the
    SHA256 hash of the verifier and comparing it to the stored challenge.
    This proves the client possesses the secret used during login initiation.

    Args:
        code_verifier (str): Base64url-encoded verifier from mobile client.
        code_challenge (str): Base64url-encoded SHA256 hash stored in DB.
        code_challenge_method (str): PKCE method (must be "S256").

    Raises:
        HTTPException: 400 Bad Request if verifier format is invalid,
            method is not S256, or verifier doesn't match challenge.
    """
    # Validate verifier format
    if not (43 <= len(code_verifier) <= 128):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code_verifier must be 43-128 characters",
        )

    if not re.match(r"^[A-Za-z0-9_-]+$", code_verifier):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code_verifier must be valid base64url",
        )

    # Verify method is S256
    if code_challenge_method != "S256":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only S256 PKCE method is supported",
        )

    # Compute SHA256 hash of verifier
    verifier_hash = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed_challenge = (
        base64.urlsafe_b64encode(verifier_hash).decode("ascii").rstrip("=")
    )

    # Constant-time comparison to prevent timing attacks
    if not _secure_compare(computed_challenge, code_challenge):
        core_logger.print_to_log(
            f"PKCE verification failed: computed={computed_challenge[:10]}..., expected={code_challenge[:10]}...",
            "warning",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid code_verifier",
        )


def _secure_compare(a: str, b: str) -> bool:
    """
    Constant-time string comparison to prevent timing attacks.

    Args:
        a (str): First string.
        b (str): Second string.

    Returns:
        bool: True if strings are equal, False otherwise.
    """
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0


# Pre-configured templates for common IdPs
IDP_TEMPLATES = {
    "authelia": {
        "name": "Authelia",
        "provider_type": "oidc",
        "issuer_url": "https://{your-authelia-domain}",
        "scopes": "openid profile email",
        "icon": "authelia",
        "user_mapping": {
            "username": ["preferred_username", "username", "email"],
            "email": ["email"],
            "name": ["name"],
        },
        "description": "Authelia - Open-source authentication and authorization server",
        "configuration_notes": "Replace {your-authelia-domain} with your Authelia server domain (e.g., auth.example.com). Configure an OIDC client in your Authelia configuration file.",
    },
    "authentik": {
        "name": "Authentik",
        "provider_type": "oidc",
        "issuer_url": "https://{your-authentik-domain}/application/o/{slug}/",
        "scopes": "openid profile email",
        "icon": "authentik",
        "user_mapping": {
            "username": ["preferred_username", "username", "email"],
            "email": ["email", "mail"],
            "name": ["name", "display_name"],
        },
        "description": "Authentik - Open-source Identity Provider",
        "configuration_notes": "Replace {your-authentik-domain} with your Authentik server domain (e.g., authentik.example.com) and {slug} with your application slug. Create an OAuth2/OIDC provider in Authentik.",
    },
    "casdoor": {
        "name": "Casdoor",
        "provider_type": "oidc",
        "issuer_url": "https://{your-casdoor-domain}",
        "scopes": "openid profile email",
        "icon": "casdoor",
        "user_mapping": {
            "username": ["preferred_username", "username", "name"],
            "email": ["email"],
            "name": ["name", "displayName"],
        },
        "description": "Casdoor - Open-source Identity and Access Management (IAM) / Single-Sign-On (SSO) platform",
        "configuration_notes": "Replace {your-casdoor-domain} with your Casdoor server domain (e.g., casdoor.example.com). Create an OAuth2/OIDC application in Casdoor admin console.",
    },
    "keycloak": {
        "name": "Keycloak",
        "provider_type": "oidc",
        "issuer_url": "https://{your-keycloak-domain}/realms/{realm}",
        "scopes": "openid profile email",
        "icon": "keycloak",
        "user_mapping": {
            "username": ["preferred_username", "username", "email"],
            "email": ["email", "mail"],
            "name": ["name", "display_name", "full_name"],
        },
        "description": "Keycloak - Open Source Identity and Access Management",
        "configuration_notes": "Replace {your-keycloak-domain} with your Keycloak server domain (e.g., keycloak.example.com) and {realm} with your realm name. Create an OIDC client in Keycloak admin console.",
    },
    "pocketid": {
        "name": "Pocket ID",
        "provider_type": "oidc",
        "issuer_url": "https://{your-pocketid-domain}",
        "scopes": "openid profile email",
        "icon": "pocketid",
        "user_mapping": {
            "username": ["preferred_username", "username", "email"],
            "email": ["email"],
            "name": ["name"],
        },
        "description": "Pocket ID - Simple OIDC provider for passwordless passkey authentication",
        "configuration_notes": "Replace {your-pocketid-domain} with your Pocket ID server domain (e.g., auth.example.com). Create a new OIDC client in Pocket ID admin panel and copy the Client ID, Client Secret, and OIDC Discovery URL.",
    },
}


def get_idp_templates() -> list[idp_schema.IdentityProviderTemplate]:
    """
    Retrieve a list of identity provider templates, excluding specific providers.

    Returns:
        list[idp_schema.IdentityProviderTemplate]:
            A list of IdentityProviderTemplate objects for all identity providers.
    """
    templates = []
    for template_id, template_data in IDP_TEMPLATES.items():
        templates.append(
            idp_schema.IdentityProviderTemplate(
                template_id=template_id, **template_data
            )
        )
    return templates


def get_idp_template(template_id: str) -> dict[str, Any] | None:
    """
    Retrieve an identity provider template by its template ID.

    Args:
        template_id (str): The unique identifier of the identity provider template.

    Returns:
        dict[str, Any] | None: The template dictionary if found, otherwise None.
    """
    return IDP_TEMPLATES.get(template_id)


async def refresh_idp_tokens_if_needed(user_id: int, db: Session) -> None:
    """
    Refreshes identity provider (IdP) tokens for a user if needed based on token expiration policies.

    This function retrieves all IdP links associated with a user and evaluates each token's
    state to determine the appropriate action: refresh if nearing expiry, clear if maximum
    age is exceeded, or skip if still valid.

    The function is designed to be non-blocking and opportunistic - errors during token
    refresh or clearing are logged but do not raise exceptions, allowing the application
    to continue normal operation even if IdP token management fails.

    Args:
        user_id (int): The ID of the user whose IdP tokens should be checked and refreshed.
        db (Session): SQLAlchemy database session for performing database operations.

    Returns:
        None: This function performs side effects (token refresh/clearing) but returns nothing.

    Raises:
        Does not raise exceptions. All errors are caught, logged, and suppressed to ensure
        IdP token management does not disrupt normal application flow.

    Notes:
        - If a user has no IdP links, the function returns early without performing any operations.
        - Token refresh attempts that fail are logged but the user session remains valid.
        - Tokens exceeding maximum age are cleared for security, requiring user re-authentication.
        - Individual IdP operation failures do not prevent checking other IdP links.
    """
    try:
        # Get all IdP links for this user
        idp_links = user_idp_crud.get_user_identity_providers_by_user_id(user_id, db)

        if not idp_links:
            # User has no IdP links - nothing to refresh
            return

        # Check each IdP link and take appropriate action
        for link in idp_links:
            try:
                # Determine what action to take for this IdP token (policy-based)
                action = idp_service.idp_service._should_refresh_idp_token(link)

                if action == idp_service.TokenAction.REFRESH:
                    # Token is close to expiry - attempt to refresh
                    core_logger.print_to_log(
                        f"Attempting to refresh IdP token for user {user_id}, idp {link.idp_id}",
                        "debug",
                    )

                    # Attempt to refresh the IdP session
                    result = await idp_service.idp_service.refresh_idp_session(
                        user_id, link.idp_id, db
                    )

                    if result:
                        core_logger.print_to_log(
                            f"Successfully refreshed IdP token for user {user_id}, idp {link.idp_id}",
                            "debug",
                        )
                    else:
                        core_logger.print_to_log(
                            f"IdP token refresh failed for user {user_id}, idp {link.idp_id}. "
                            "User may need to re-authenticate with IdP later.",
                            "debug",
                        )

                elif action == idp_service.TokenAction.CLEAR:
                    # Token has exceeded maximum age - clear it for security
                    core_logger.print_to_log(
                        f"Clearing expired IdP token (max age exceeded) for user {user_id}, idp {link.idp_id}",
                        "info",
                    )

                    success = user_idp_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                        user_id, link.idp_id, db
                    )

                    if success:
                        core_logger.print_to_log(
                            f"Successfully cleared expired IdP token for user {user_id}, idp {link.idp_id}. "
                            "User will need to re-authenticate with IdP.",
                            "info",
                        )
                    else:
                        core_logger.print_to_log(
                            f"Failed to clear expired IdP token for user {user_id}, idp {link.idp_id}",
                            "warning",
                        )

                else:  # idp_service.TokenAction.SKIP
                    # Token is still valid and not close to expiry - no action needed
                    pass

            except Exception as err:
                # Log individual IdP operation failure but continue with other IdPs
                core_logger.print_to_log(
                    f"Error checking/refreshing IdP token for user {user_id}, idp {link.idp_id}: {err}",
                    "warning",
                    exc=err,
                )
                # Continue to next IdP link

    except Exception as err:
        # Catch-all for unexpected errors (e.g., database query failure)
        core_logger.print_to_log(
            f"Error retrieving IdP links for user {user_id}: {err}",
            "warning",
            exc=err,
        )
        # Don't raise - IdP token refresh is opportunistic and non-blocking


async def clear_all_idp_tokens(
    user_id: int, db: Session, revoke_at_idp: bool = False
) -> None:
    """
    Clear all IdP (Identity Provider) refresh tokens for a user.

    This function retrieves all IdP links associated with a user and clears their
    refresh tokens. It supports optional revocation at the IdP level before clearing
    tokens locally.

    Args:
        user_id (int): The ID of the user whose IdP tokens should be cleared.
        db (Session): The database session to use for queries.
        revoke_at_idp (bool, optional): If True, attempts to revoke tokens at the
            IdP provider level (RFC 7009) before clearing locally. Defaults to False.

    Returns:
        None

    Raises:
        This function does not raise exceptions. All errors are logged and handled
        gracefully to ensure logout processes are not interrupted.

    Notes:
        - If no IdP links exist for the user, the function returns early.
        - Token revocation at the IdP is best-effort; local clearing always proceeds
          regardless of revocation success or failure.
        - Individual IdP token clearing failures do not prevent clearing tokens for
          other IdPs.
        - All errors are logged with appropriate severity levels (debug, info, warning).
    """
    try:
        # Get all IdP links for this user
        idp_links = user_idp_crud.get_user_identity_providers_by_user_id(user_id, db)

        if not idp_links:
            # User has no IdP links - nothing to clear
            return

        # Clear tokens for each IdP link
        for link in idp_links:
            try:
                # Optionally attempt to revoke token at IdP first (RFC 7009)
                if revoke_at_idp:
                    try:
                        revoked = await idp_service.idp_service.revoke_idp_token(
                            user_id, link.idp_id, db
                        )
                        if revoked:
                            core_logger.print_to_log(
                                f"Revoked IdP token at provider for user {user_id}, idp {link.idp_id}",
                                "info",
                            )
                        else:
                            core_logger.print_to_log(
                                f"IdP token revocation not supported or failed for user {user_id}, idp {link.idp_id}. "
                                "Will clear locally.",
                                "debug",
                            )
                    except Exception as revoke_err:
                        # Log revocation failure but continue with local clearing
                        core_logger.print_to_log(
                            f"Error revoking IdP token for user {user_id}, idp {link.idp_id}: {revoke_err}. "
                            "Will clear locally.",
                            "warning",
                            exc=revoke_err,
                        )

                # Always clear locally regardless of revocation result
                success = user_idp_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                    user_id, link.idp_id, db
                )

                if success:
                    core_logger.print_to_log(
                        f"Cleared IdP refresh token for user {user_id}, idp {link.idp_id} on logout",
                        "debug",
                    )
                else:
                    core_logger.print_to_log(
                        f"No IdP refresh token to clear for user {user_id}, idp {link.idp_id}",
                        "debug",
                    )

            except Exception as err:
                # Log individual IdP token clearing failure but continue with other IdPs
                core_logger.print_to_log(
                    f"Error clearing IdP token for user {user_id}, idp {link.idp_id}: {err}",
                    "warning",
                    exc=err,
                )
                # Continue to next IdP link

    except Exception as err:
        # Catch-all for unexpected errors (e.g., database query failure)
        core_logger.print_to_log(
            f"Error retrieving IdP links for user {user_id} during logout: {err}",
            "warning",
            exc=err,
        )
        # Don't raise - IdP token clearing is a best-effort security measure
