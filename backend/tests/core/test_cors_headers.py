"""The CORS allow-list must cover every header the API's own routes declare.

A header the routes accept but CORS does not allow is worse than a header that
is ignored: the browser's *preflight* fails, so the request is never sent at all.
That is how ``If-Match`` shipped — the conditional-write header was declared on
``PATCH /activities/{id}``, never added to the allow-list, and every edit from a
browser died at the preflight with "does not have HTTP ok status", with nothing
in the backend log because the request never arrived.

Deriving the expectation from the OpenAPI schema rather than hard-coding a list
is the point: the next route that declares a header fails here instead of in a
browser.
"""

from scripts.export_openapi import build_openapi

import core.middleware as core_middleware

# Headers supplied by the transport or by a security scheme rather than declared
# as a route parameter, so they never appear as an OpenAPI header parameter.
_NON_PARAMETER_HEADERS = {"authorization", "content-type"}


def _declared_header_parameters() -> set[str]:
    """Return every header name the API's routes declare as a parameter."""
    schema = build_openapi()
    return {
        parameter["name"].lower()
        for path in schema.get("paths", {}).values()
        for operation in path.values()
        if isinstance(operation, dict)
        for parameter in operation.get("parameters", [])
        if parameter.get("in") == "header"
    }


class TestCorsAllowHeaders:
    def test_every_declared_request_header_is_allowed(self):
        allowed = {header.lower() for header in core_middleware.CORS_ALLOW_HEADERS}

        missing = sorted(_declared_header_parameters() - allowed - _NON_PARAMETER_HEADERS)

        assert missing == []

    def test_if_match_is_allowed(self):
        """The conditional-write header; without it no browser can send a PATCH."""
        assert "If-Match" in core_middleware.CORS_ALLOW_HEADERS

    def test_etag_is_exposed(self):
        """The client cannot echo back a tag it is not permitted to read."""
        assert "ETag" in core_middleware.CORS_EXPOSE_HEADERS
