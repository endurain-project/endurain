"""Utility helpers for identity providers."""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import core.exceptions as core_exceptions
import core.redirect_schemes as core_redirect_schemes
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.contracts as identity_provider_contracts


def _custom_scheme(value: str) -> str | None:
    """Return the lower-cased scheme of a ``scheme://`` value, or None when it has none."""
    if "://" not in value:
        return None
    return value.split("://", 1)[0].lower()


def normalize_issuer_url(issuer_url: str) -> str:
    """Return an issuer URL without its trailing slashes, the form in which two issuers are compared.

    Equals the SQL ``rtrim(issuer_url, '/')`` behind the unique index on the issuer.

    Args:
        issuer_url: An issuer URL.

    Returns:
        The URL with every trailing slash removed.
    """
    return issuer_url.rstrip("/")


def requires_id_token(idp: identity_provider_contracts.IdentityProviderState) -> bool:
    """Return whether a sign-in through a provider must carry a verified ID token, and so its nonce.

    An OpenID Connect provider always issues one, and so does an OAuth 2.0 provider asked for the ``openid`` scope.
    A provider with no scopes configured is asked for the default ones, which include ``openid``.

    Args:
        idp: The provider.

    Returns:
        Whether the ID token is mandatory.
    """
    if idp.provider_type == idp_constants.ProviderType.OIDC:
        return True
    return "openid" in (idp.scopes or idp_constants.DEFAULT_SCOPES).split()


def validate_redirect_url(redirect: str | None, allowed_schemes: set[str], allowed_uris: set[str]) -> None:
    """Validate the redirect URL to prevent open redirect vulnerabilities.

    Allows only relative paths (starting with '/') and custom URI
    schemes explicitly configured via ALLOWED_REDIRECT_SCHEMES. When
    ALLOWED_REDIRECT_URIS is set, a custom-scheme redirect must instead
    equal one of those addresses (the scheme in any letter case, the rest
    exactly, query and fragment included) and the schemes are ignored.
    External HTTP/HTTPS URLs are always rejected, in any letter case,
    and so are the unsafe schemes in ``UNSAFE_REDIRECT_SCHEMES``, even
    when they are listed in ``allowed_schemes``.

    Args:
        redirect: The redirect URL string to validate, or None.
        allowed_schemes: Custom URI schemes a redirect may use.
        allowed_uris: Exact custom-scheme addresses a redirect may use; when not empty, they replace the schemes.

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
    if value.lower().startswith(("http://", "https://")):
        raise core_exceptions.InvalidInputError(
            "External HTTP redirects are not allowed. Use a relative path or a configured custom scheme."
        )

    # Handle custom URI schemes (e.g., gadgetbridge://callback)
    scheme = _custom_scheme(value)
    if scheme is not None:
        if scheme in core_redirect_schemes.UNSAFE_REDIRECT_SCHEMES:
            raise core_exceptions.InvalidInputError(f"Redirect scheme '{scheme}' is not allowed.")
        if allowed_uris:
            if core_redirect_schemes.normalise_redirect_uri(value) not in allowed_uris:
                raise core_exceptions.InvalidInputError(
                    "Redirect address is not allowed. Configure ALLOWED_REDIRECT_URIS to permit it."
                )
        elif scheme not in allowed_schemes:
            raise core_exceptions.InvalidInputError(
                f"Redirect scheme '{scheme}' is not allowed. "
                "Configure ALLOWED_REDIRECT_SCHEMES to permit custom URI schemes."
            )
        # Custom redirect is allowed — no further checks needed
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
    redirect target becomes the authoritative signal. An unsafe scheme
    (``UNSAFE_REDIRECT_SCHEMES``), including HTTP/HTTPS in any letter case, is
    never a custom-scheme redirect.
    """
    if not redirect or not redirect.strip():
        return False

    scheme = _custom_scheme(redirect.strip())
    return scheme is not None and scheme not in core_redirect_schemes.UNSAFE_REDIRECT_SCHEMES


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


def build_redirect_uri(frontend_host: str, idp_slug: str) -> str:
    """Return the callback URL an identity provider redirects the browser to.

    Args:
        frontend_host: Public host the application is served from.
        idp_slug: Slug of the identity provider.

    Returns:
        The complete redirect URI for the provider.
    """
    return f"{frontend_host}/api/v1/public/idp/callback/{idp_slug}"
