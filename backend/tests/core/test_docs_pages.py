"""Tests for the API documentation pages and the policy that lets their inline script run."""

import base64
import hashlib
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.docs_pages as core_docs_pages
from core.middleware import SecurityHeadersMiddleware

_INLINE_SCRIPT = re.compile(r"<script>(.*?)</script>", re.DOTALL)


def _client() -> TestClient:
    app = FastAPI(docs_url=None, redoc_url=None)
    app.add_middleware(SecurityHeadersMiddleware)
    core_docs_pages.register_routes(app, "/api/v1/docs", "/api/v1/redoc")
    return TestClient(app)


def _directive(csp: str, name: str) -> str:
    return next(d for d in csp.split("; ") if d.startswith(f"{name} "))


@pytest.mark.parametrize("path", ["/api/v1/docs", "/api/v1/redoc", "/api/v1/docs/oauth2-redirect"])
def test_every_inline_script_is_allowed_by_the_page_policy_by_hash(path):
    response = _client().get(path)

    assert response.status_code == 200
    script_src = _directive(response.headers["Content-Security-Policy"], "script-src")
    assert "'unsafe-inline'" not in script_src
    for script in _INLINE_SCRIPT.findall(response.text):
        digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
        assert f"'sha256-{digest}'" in script_src


def test_swagger_page_has_inline_script_and_loads_its_bundle_from_the_cdn():
    response = _client().get("/api/v1/docs")

    assert _INLINE_SCRIPT.findall(response.text)
    assert "https://cdn.jsdelivr.net" in _directive(response.headers["Content-Security-Policy"], "script-src")
    assert "https://cdn.jsdelivr.net" in _directive(response.headers["Content-Security-Policy"], "style-src")


def test_docs_policy_keeps_the_header_restrictions():
    csp = _client().get("/api/v1/docs").headers["Content-Security-Policy"]

    assert "frame-ancestors 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "object-src 'none'" in csp
