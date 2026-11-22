"""The Swagger UI and ReDoc pages, served with a policy that allows exactly their own inline script.

FastAPI's pages embed an inline script, which the policy of every other HTML page refuses. These routes add the SHA-256
hash of each inline script the page carries to the page's ``script-src``, so nothing else inline can run.
"""

import base64
import hashlib
import re

from fastapi import FastAPI, Request
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.responses import HTMLResponse

#: The CDN FastAPI loads the Swagger UI and ReDoc bundles from.
_CDN = "https://cdn.jsdelivr.net"

_INLINE_SCRIPT = re.compile(r"<script>(.*?)</script>", re.DOTALL)


def _script_hash(script: str) -> str:
    """Return the CSP source expression that allows one inline script.

    Args:
        script: The exact text between the ``<script>`` tags.

    Returns:
        The ``'sha256-...'`` source.
    """
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    return f"'sha256-{digest}'"


def _with_policy(page: HTMLResponse) -> HTMLResponse:
    """Set the page's Content-Security-Policy from the inline scripts it carries.

    Swagger UI and ReDoc style themselves at runtime, so their policy keeps ``'unsafe-inline'`` for styles only.

    Args:
        page: A response built by one of FastAPI's documentation helpers.

    Returns:
        The same response, with its policy set.
    """
    hashes = " ".join(_script_hash(script) for script in _INLINE_SCRIPT.findall(bytes(page.body).decode()))
    script_src = f"'self' {_CDN} {hashes}".strip()
    page.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data: https://fastapi.tiangolo.com; "
        f"style-src 'self' 'unsafe-inline' {_CDN}; "
        f"script-src {script_src}; "
        "base-uri 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'"
    )
    return page


def register_routes(app: FastAPI, docs_url: str, redoc_url: str) -> None:
    """Serve the Swagger UI, its OAuth2 redirect page and ReDoc.

    Args:
        app: The application to add the routes to; it must have been built with ``docs_url`` and ``redoc_url`` unset.
        docs_url: Where Swagger UI is served.
        redoc_url: Where ReDoc is served.
    """
    oauth2_redirect_url = f"{docs_url}/oauth2-redirect"

    async def swagger_ui(request: Request) -> HTMLResponse:
        root_path = request.scope.get("root_path", "").rstrip("/")
        return _with_policy(
            get_swagger_ui_html(
                openapi_url=f"{root_path}{app.openapi_url}",
                title=f"{app.title} - Swagger UI",
                oauth2_redirect_url=f"{root_path}{oauth2_redirect_url}",
            )
        )

    async def swagger_ui_oauth2_redirect(request: Request) -> HTMLResponse:
        return _with_policy(get_swagger_ui_oauth2_redirect_html())

    async def redoc(request: Request) -> HTMLResponse:
        root_path = request.scope.get("root_path", "").rstrip("/")
        return _with_policy(get_redoc_html(openapi_url=f"{root_path}{app.openapi_url}", title=f"{app.title} - ReDoc"))

    app.add_route(docs_url, swagger_ui, include_in_schema=False)
    app.add_route(oauth2_redirect_url, swagger_ui_oauth2_redirect, include_in_schema=False)
    app.add_route(redoc_url, redoc, include_in_schema=False)
