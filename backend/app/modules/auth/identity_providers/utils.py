"""Utility helpers and pre-configured templates for identity providers."""

import base64
import hashlib
import hmac
import re
from typing import Any

import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.identity_providers.schema as idp_schema

logger = core_logger.get_logger(__name__)


def validate_redirect_url(redirect: str | None, allowed_schemes: set[str]) -> None:
    """Validate the redirect URL to prevent open redirect vulnerabilities.

    Allows only relative paths (starting with '/') and custom URI
    schemes explicitly configured via ALLOWED_REDIRECT_SCHEMES.
    External HTTP/HTTPS URLs are always rejected.

    Args:
        redirect: The redirect URL string to validate, or None.

        allowed_schemes: Value used by this operation.

    Raises:
        HTTPException: 400 Bad Request if the redirect URL is
            invalid, uses a disallowed scheme, is an external
            HTTP/HTTPS URL, or contains control characters or path
            traversal sequences.
    """
    if not redirect or not redirect.strip():
        return

    # Checked on the raw value, before stripping: the caller stores what it passed
    # in, and a browser's URL parser drops tab, CR and LF anywhere in a URL, so
    # "/<tab>/host" would be read as the protocol-relative "//host".
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in redirect):
        raise core_exceptions.InvalidInputError("Redirect contains control characters.")

    value = redirect.strip()

    # Reject external HTTP/HTTPS URLs (open redirect prevention)
    if value.startswith("http://") or value.startswith("https://"):
        raise core_exceptions.InvalidInputError(
            "External HTTP redirects are not allowed. Use a relative path or a configured custom scheme."
        )

    # Handle custom URI schemes (e.g., gadgetbridge://callback)
    if "://" in value:
        scheme = value.split("://", 1)[0].lower()
        allowed = allowed_schemes
        if scheme not in allowed:
            raise core_exceptions.InvalidInputError(
                f"Redirect scheme '{scheme}' is not allowed. Configure ALLOWED_REDIRECT_SCHEMES to permit custom URI schemes."
            )
        # Custom scheme is allowed — no further checks needed
        return

    # Relative paths must start with '/'
    if not value.startswith("/"):
        raise core_exceptions.InvalidInputError(
            "Redirect must be a relative path starting with '/' or a configured custom URI scheme."
        )

    # Reject path traversal sequences
    if ".." in value or "\\" in value or value.startswith("//"):
        raise core_exceptions.InvalidInputError("Redirect path contains disallowed sequences.")


def is_custom_scheme_redirect(redirect: str | None) -> bool:
    """Return ``True`` when the redirect is a validated custom URI scheme.

    This preserves mobile intent across the browser-based OAuth round trip.
    The browser leg cannot reliably carry ``X-Client-Type``, so the validated
    redirect target becomes the authoritative signal.
    """
    if not redirect or not redirect.strip():
        return False

    value = redirect.strip()

    if value.startswith("http://") or value.startswith("https://"):
        return False

    return "://" in value


def validate_pkce_verifier(code_verifier: str, code_challenge: str, code_challenge_method: str) -> None:
    """Validate PKCE code_verifier and verify it matches the code_challenge.

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
        raise core_exceptions.InvalidInputError("code_verifier must be 43-128 characters")

    if not re.match(r"^[A-Za-z0-9_-]+$", code_verifier):
        raise core_exceptions.InvalidInputError("code_verifier must be valid base64url")

    # Verify method is S256
    if code_challenge_method != "S256":
        raise core_exceptions.InvalidInputError("Only S256 PKCE method is supported")

    # Compute SHA256 hash of verifier
    verifier_hash = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed_challenge = base64.urlsafe_b64encode(verifier_hash).decode("ascii").rstrip("=")

    # Constant-time comparison to prevent timing attacks
    if not _secure_compare(computed_challenge, code_challenge):
        logger.warning(
            "PKCE verification failed: computed=<value_1>..., expected=<value_2>...",
            extra=core_logger.context(value_1=computed_challenge[:10], value_2=code_challenge[:10]),
        )
        raise core_exceptions.InvalidInputError("Invalid code_verifier")


def _secure_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks.

    Uses ``hmac.compare_digest`` to avoid both character-by-
    character and length timing leaks.

    Args:
        a: First string.
        b: Second string.

    Returns:
        True if strings are equal, False otherwise.
    """
    return hmac.compare_digest(a.encode(), b.encode())


# Pre-configured templates for common IdPs
IDP_TEMPLATES: dict[str, dict[str, Any]] = {
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
    """Retrieve a list of identity provider templates, excluding specific providers.

    Returns:
        list[idp_schema.IdentityProviderTemplate]:
            A list of IdentityProviderTemplate objects for all identity providers.
    """
    templates = []
    for template_id, template_data in IDP_TEMPLATES.items():
        templates.append(idp_schema.IdentityProviderTemplate(template_id=template_id, **template_data))
    return templates


def get_idp_template(template_id: str) -> dict[str, Any] | None:
    """Retrieve an identity provider template by its template ID.

    Args:
        template_id (str): The unique identifier of the identity provider template.

    Returns:
        dict[str, Any] | None: The template dictionary if found, otherwise None.
    """
    return IDP_TEMPLATES.get(template_id)
