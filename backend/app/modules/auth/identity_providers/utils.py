"""Utility helpers and pre-configured templates for identity providers."""

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import core.exceptions as core_exceptions
import modules.auth.identity_providers.schema as idp_schema


def validate_redirect_url(redirect: str | None, allowed_schemes: set[str]) -> None:
    """Validate the redirect URL to prevent open redirect vulnerabilities.

    Allows only relative paths (starting with '/') and custom URI
    schemes explicitly configured via ALLOWED_REDIRECT_SCHEMES.
    External HTTP/HTTPS URLs are always rejected.

    Args:
        redirect: The redirect URL string to validate, or None.
        allowed_schemes: Custom URI schemes a redirect may use.

    Raises:
        InvalidInputError: If the redirect URL is
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
                f"Redirect scheme '{scheme}' is not allowed. "
                "Configure ALLOWED_REDIRECT_SCHEMES to permit custom URI schemes."
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


def append_query_params(url: str, params: dict[str, str]) -> str:
    """Append query parameters to a URL or relative path, preserving any existing query.

    Args:
        url: An absolute URL or a relative path.
        params: The parameters to add; an existing parameter of the same name is replaced.

    Returns:
        The URL with the parameters in its query.
    """
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def build_link_result_url(host: str, redirect_path: str | None, idp_name: str | None, *, success: bool) -> str:
    """Build the post-link redirect that carries the result to the originating client.

    Honors a caller-supplied return path captured at link initiation (validated there against open
    redirects): a relative path is resolved against the frontend host, while a custom URI scheme is handed
    off directly to the native client. Falls back to the security settings path when no return path was
    provided.

    Args:
        host: The configured frontend host.
        redirect_path: The validated return path or custom scheme, or None.
        idp_name: Provider display name (included on success).
        success: Whether the link succeeded.

    Returns:
        The absolute URL (or custom-scheme URL) to redirect the browser to.
    """
    params = {"idp_link": "success" if success else "error"}
    if success and idp_name is not None:
        params["idp_name"] = idp_name
    if redirect_path and is_custom_scheme_redirect(redirect_path):
        return append_query_params(redirect_path, params)
    base = redirect_path or "/settings/security"
    return f"{host}{append_query_params(base, params)}"


def build_step_up_result_url(host: str, redirect_path: str | None, result: dict[str, str]) -> str:
    """Build the redirect that hands a step-up's outcome back to the page that started it.

    The outcome travels in the fragment: a browser never sends it to a server, so a ticket stays out of access
    logs, proxies and ``Referer`` headers.

    Args:
        host: The configured frontend host.
        redirect_path: The validated relative return path, or None.
        result: The outcome, ``step_up_ticket`` on success or ``step_up_error`` on failure.

    Returns:
        The absolute URL to redirect the browser to.
    """
    parts = urlsplit(redirect_path or "/settings/security")
    return f"{host}{urlunsplit(('', '', parts.path, parts.query, urlencode(result)))}"


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
        "configuration_notes": (
            "Replace {your-authelia-domain} with your Authelia server domain (e.g., auth.example.com). "
            "Configure an OIDC client in your Authelia configuration file."
        ),
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
        "configuration_notes": (
            "Replace {your-authentik-domain} with your Authentik server domain (e.g., authentik.example.com) "
            "and {slug} with your application slug. Create an OAuth2/OIDC provider in Authentik."
        ),
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
        "configuration_notes": (
            "Replace {your-casdoor-domain} with your Casdoor server domain (e.g., casdoor.example.com). "
            "Create an OAuth2/OIDC application in Casdoor admin console."
        ),
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
        "configuration_notes": (
            "Replace {your-keycloak-domain} with your Keycloak server domain (e.g., keycloak.example.com) "
            "and {realm} with your realm name. Create an OIDC client in Keycloak admin console."
        ),
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
        "configuration_notes": (
            "Replace {your-pocketid-domain} with your Pocket ID server domain (e.g., auth.example.com). "
            "Create a new OIDC client in Pocket ID admin panel and copy the Client ID, Client Secret, and "
            "OIDC Discovery URL."
        ),
    },
}


def get_idp_templates() -> list[idp_schema.IdentityProviderTemplateRead]:
    """Retrieve a list of identity provider templates, excluding specific providers.

    Returns:
        list[idp_schema.IdentityProviderTemplateRead]:
            A list of IdentityProviderTemplateRead objects for all identity providers.
    """
    templates = []
    for template_id, template_data in IDP_TEMPLATES.items():
        templates.append(idp_schema.IdentityProviderTemplateRead(template_id=template_id, **template_data))
    return templates


def get_idp_template(template_id: str) -> dict[str, Any] | None:
    """Retrieve an identity provider template by its template ID.

    Args:
        template_id (str): The unique identifier of the identity provider template.

    Returns:
        dict[str, Any] | None: The template dictionary if found, otherwise None.
    """
    return IDP_TEMPLATES.get(template_id)


def build_redirect_uri(frontend_host: str, idp_slug: str) -> str:
    """Return the callback URL an identity provider redirects the browser to.

    Args:
        frontend_host: Public host the application is served from.
        idp_slug: Slug of the identity provider.

    Returns:
        The complete redirect URI for the provider.
    """
    return f"{frontend_host}/api/v1/public/idp/callback/{idp_slug}"
