"""The browser security headers every response carries.

Kept apart from :mod:`core.middleware` so the handler that answers an unhandled error, which Starlette runs outside
every middleware, sets the same headers as the middleware does.
"""

from starlette.responses import Response

import core.config as core_config
import core.environment as core_environment

#: The policy of a JSON response: it renders nothing, so it may load nothing and may not be framed.
API_CONTENT_SECURITY_POLICY = "default-src 'none'; frame-ancestors 'none'"


def is_json(content_type: str | None) -> bool:
    """Tell whether a ``Content-Type`` names a JSON media type.

    Args:
        content_type: The header value, parameters included.

    Returns:
        True for ``application/json`` and any ``+json`` type, such as ``application/problem+json``.
    """
    media_type = (content_type or "").split(";")[0].strip().lower()
    return media_type == "application/json" or media_type.endswith("+json")


def is_html(content_type: str | None) -> bool:
    """Tell whether a ``Content-Type`` names an HTML document.

    Args:
        content_type: The header value, parameters included.

    Returns:
        True for ``text/html``.
    """
    return "text/html" in (content_type or "").lower()


def apply(response: Response) -> None:
    """Set the security headers that do not depend on the page, and the policy of a JSON response.

    The policy of an HTML page names the tile and storage origins, so :class:`core.middleware.SecurityHeadersMiddleware`
    sets it.

    Args:
        response: The response to add the headers to.
    """
    headers = response.headers
    headers["X-Content-Type-Options"] = "nosniff"
    headers["X-Frame-Options"] = "DENY"
    # Disable legacy browser XSS auditors; CSP is the modern control.
    headers["X-XSS-Protection"] = "0"
    # A page sends no Referer: its URL can carry a reset token, a verification token or an SSO session id. The map tile
    # requests set their own policy, because tile servers can require a Referer.
    headers["Referrer-Policy"] = (
        "no-referrer" if is_html(headers.get("content-type")) else "strict-origin-when-cross-origin"
    )
    headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    # Another origin cannot hold a reference to a window of this app, and only the same site may embed a resource.
    headers["Cross-Origin-Opener-Policy"] = "same-origin"
    headers["Cross-Origin-Resource-Policy"] = "same-site"
    if core_environment.is_deployed_environment(core_config.settings.ENVIRONMENT):
        hsts = "max-age=31536000; includeSubDomains"
        headers["Strict-Transport-Security"] = f"{hsts}; preload" if core_config.settings.HSTS_PRELOAD else hsts
    if is_json(headers.get("content-type")):
        headers["Content-Security-Policy"] = API_CONTENT_SECURITY_POLICY
