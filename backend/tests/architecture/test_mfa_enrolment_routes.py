"""The requests an account that must enrol MFA may still make exist, and need authentication.

``modules.auth.constants.MFA_ENROLMENT_ROUTES`` names them by method and route template, so a rename of one of the
routes would silently turn the enrolment page into a dead end. This test fails the rename instead. It reads the
OpenAPI document, which carries the full template of every route.
"""

import functools
import importlib.util
import pathlib
from typing import Any

import modules.auth.constants as auth_constants

_API_PREFIX = "/api/v1"


@functools.cache
def _openapi() -> dict[str, Any]:
    """Return the OpenAPI document ``scripts/export_openapi.py`` builds, built once per run."""
    spec = importlib.util.spec_from_file_location("export_openapi", pathlib.Path("scripts") / "export_openapi.py")
    assert spec is not None and spec.loader is not None
    export_openapi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(export_openapi)
    return export_openapi.build_openapi()


def test_every_exempt_request_is_a_route_of_the_api():
    paths = _openapi()["paths"]

    missing = {
        (method, template)
        for method, template in auth_constants.MFA_ENROLMENT_ROUTES
        if method.lower() not in paths.get(_API_PREFIX + template, {})
    }

    assert not missing


def test_every_exempt_route_is_authenticated():
    """An exemption from the enrolment refusal is not an exemption from authentication."""
    paths = _openapi()["paths"]

    unauthenticated = {
        (method, template)
        for method, template in auth_constants.MFA_ENROLMENT_ROUTES
        if not paths[_API_PREFIX + template][method.lower()].get("security")
    }

    assert not unauthenticated
