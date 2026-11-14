"""Tests for the security headers, the cookie-route origin check and the tile-domain refresh."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.config as core_config
from core.middleware import CookieRouteOriginMiddleware

ALLOWED_ORIGIN = "https://app.example"
REFRESH_PATH = f"{core_config.ROOT_PATH}/auth/refresh"
LOGOUT_PATH = f"{core_config.ROOT_PATH}/auth/logout"
WEB = {"X-Client-Type": "web"}


@pytest.fixture
def client():
    """Create a test client for an app that checks the origin of the two cookie routes.

    Returns:
        A client for an app whose allowed origins are ``ALLOWED_ORIGIN`` only.
    """
    app = FastAPI()
    app.state.cors_allow_origins = [ALLOWED_ORIGIN]
    app.add_middleware(CookieRouteOriginMiddleware)

    @app.post(REFRESH_PATH)
    async def refresh():
        return {"message": "refresh"}

    @app.post(LOGOUT_PATH)
    async def logout():
        return {"message": "logout"}

    @app.post(f"{core_config.ROOT_PATH}/other")
    async def other():
        return {"message": "other"}

    return TestClient(app)


class TestCookieRouteOriginMiddleware:
    """A web request to a cookie route must name an allowed origin."""

    @pytest.mark.parametrize("path", [REFRESH_PATH, LOGOUT_PATH])
    def test_an_allowed_origin_passes(self, client, path):
        response = client.post(path, headers={**WEB, "Origin": ALLOWED_ORIGIN})

        assert response.status_code == 200

    @pytest.mark.parametrize("path", [REFRESH_PATH, LOGOUT_PATH])
    @pytest.mark.parametrize("origin", ["https://evil.example", "null", "https://app.example.evil.example"])
    def test_a_foreign_origin_is_refused(self, client, path, origin):
        response = client.post(path, headers={**WEB, "Origin": origin})

        assert response.status_code == 403
        assert response.headers["content-type"].startswith("application/problem+json")
        body = response.json()
        assert body["type"] == "urn:endurain:error:permission-denied"
        assert body["detail"] == "Origin not allowed"

    @pytest.mark.parametrize("path", [REFRESH_PATH, LOGOUT_PATH])
    def test_a_web_request_without_origin_is_refused(self, client, path):
        assert client.post(path, headers=WEB).status_code == 403

    @pytest.mark.parametrize("path", [REFRESH_PATH, LOGOUT_PATH])
    def test_cross_site_fetch_metadata_is_refused_even_from_an_allowed_origin(self, client, path):
        headers = {**WEB, "Origin": ALLOWED_ORIGIN, "Sec-Fetch-Site": "cross-site"}

        assert client.post(path, headers=headers).status_code == 403

    @pytest.mark.parametrize("site", ["same-origin", "same-site", "none"])
    def test_other_fetch_metadata_passes(self, client, site):
        headers = {**WEB, "Origin": ALLOWED_ORIGIN, "Sec-Fetch-Site": site}

        assert client.post(REFRESH_PATH, headers=headers).status_code == 200

    def test_another_route_is_not_checked(self, client):
        response = client.post(f"{core_config.ROOT_PATH}/other", headers={**WEB, "Origin": "https://evil.example"})

        assert response.status_code == 200

    @pytest.mark.parametrize("headers", [{}, {"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}])
    def test_a_mobile_client_is_not_checked(self, client, headers):
        response = client.post(REFRESH_PATH, headers={**headers, "X-Client-Type": "mobile"})

        assert response.status_code == 200


class TestSecurityHeadersMiddleware:
    """Tests for SecurityHeadersMiddleware in core.middleware."""

    def test_all_security_headers_present_in_development(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        client = TestClient(app)

        with patch("core.middleware.core_config.settings.ENVIRONMENT", "development"):
            response = client.get("/test")

        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "0"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert response.headers["Permissions-Policy"] == "geolocation=(), microphone=(), camera=()"
        assert "Strict-Transport-Security" not in response.headers
        assert "Server" not in response.headers

    @pytest.mark.parametrize("path", ["/login", "/reset-password", "/verify-email", "/activities/1", "/"])
    def test_every_html_page_sends_no_referrer(self, path):
        """A credential in a page URL never reaches another page as a Referer, and no other page leaks its path."""
        from fastapi.responses import HTMLResponse

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get(path)
        async def page():
            return HTMLResponse("<html></html>")

        response = TestClient(app).get(path)

        assert response.headers["Referrer-Policy"] == "no-referrer"

    def test_json_response_keeps_the_origin_only_referrer_policy(self):
        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/login")
        async def endpoint():
            return {"message": "ok"}

        response = TestClient(app).get("/login")

        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_hsts_header_present_in_production(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        client = TestClient(app)

        with patch("core.middleware.core_config.settings.ENVIRONMENT", "production"):
            response = client.get("/test")

        assert response.status_code == 200
        assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"

    @pytest.mark.parametrize(
        ("preload", "expected"),
        [
            (False, "max-age=31536000; includeSubDomains"),
            (True, "max-age=31536000; includeSubDomains; preload"),
        ],
    )
    def test_hsts_preload_directive_follows_the_setting(self, preload, expected):
        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        with (
            patch("core.middleware.core_config.settings.ENVIRONMENT", "production"),
            patch("core.middleware.core_config.settings.HSTS_PRELOAD", preload),
        ):
            response = TestClient(app).get("/test")

        assert response.headers["Strict-Transport-Security"] == expected

    def test_hsts_preload_is_not_sent_outside_deployed_environments(self):
        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        with (
            patch("core.middleware.core_config.settings.ENVIRONMENT", "development"),
            patch("core.middleware.core_config.settings.HSTS_PRELOAD", True),
        ):
            response = TestClient(app).get("/test")

        assert "Strict-Transport-Security" not in response.headers

    def test_hsts_header_present_in_demo(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "ok"}

        client = TestClient(app)

        with patch("core.middleware.core_config.settings.ENVIRONMENT", "demo"):
            response = client.get("/test")

        assert response.status_code == 200
        assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"

    def test_csp_header_present_for_html_response(self):
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
        from fastapi.testclient import TestClient

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/html")
        async def html_endpoint():
            return HTMLResponse("<html><body>Hello</body></html>")

        client = TestClient(app)
        response = client.get("/html")

        assert response.status_code == 200
        csp = response.headers.get("Content-Security-Policy")
        assert csp is not None
        assert "default-src 'self'" in csp

    def test_json_response_gets_the_policy_that_loads_nothing(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/json")
        async def json_endpoint():
            return {"message": "ok"}

        client = TestClient(app)
        response = client.get("/json")

        assert response.status_code == 200
        assert response.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"

    def test_server_header_removed_when_present(self):
        from fastapi import FastAPI
        from fastapi.responses import Response
        from fastapi.testclient import TestClient

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/with-server")
        async def with_server():
            return Response("ok", headers={"Server": "EvilServer/1.0"})

        client = TestClient(app)
        response = client.get("/with-server")

        assert "Server" not in response.headers

    def test_html_csp_restricts_base_uri_and_plugins(self):
        from fastapi.responses import HTMLResponse

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/html")
        async def html_endpoint():
            return HTMLResponse("<html></html>")

        directives = TestClient(app).get("/html").headers["Content-Security-Policy"].split("; ")

        assert "base-uri 'self'" in directives
        assert "object-src 'none'" in directives

    def test_html_csp_allows_no_inline_style(self):
        from fastapi.responses import HTMLResponse

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/html")
        async def html_endpoint():
            return HTMLResponse("<html></html>")

        csp = TestClient(app).get("/html").headers["Content-Security-Policy"]
        style_src = next(d for d in csp.split("; ") if d.startswith("style-src "))

        assert "'unsafe-inline'" not in style_src

    def test_html_csp_allows_no_inline_script(self):
        from fastapi.responses import HTMLResponse

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/html")
        async def html_endpoint():
            return HTMLResponse("<html></html>")

        csp = TestClient(app).get("/html").headers["Content-Security-Policy"]
        script_src = next(d for d in csp.split("; ") if d.startswith("script-src "))

        assert "'unsafe-inline'" not in script_src

    def test_a_route_policy_is_kept(self):
        from fastapi.responses import HTMLResponse

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/html")
        async def html_endpoint():
            return HTMLResponse("<html></html>", headers={"Content-Security-Policy": "default-src 'none'"})

        response = TestClient(app).get("/html")

        assert response.headers["Content-Security-Policy"] == "default-src 'none'"

    def test_csp_has_no_tile_domains_until_the_app_seeds_them(self):
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
        from fastapi.testclient import TestClient

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/html")
        async def html_endpoint():
            return HTMLResponse("<html><body>Hello</body></html>")

        client = TestClient(app)
        response = client.get("/html")

        # The composition root seeds app.state at startup; an app that never ran
        # it gets a restrictive CSP instead of core guessing a tile provider.
        csp = response.headers["Content-Security-Policy"]
        assert "img-src 'self' data:" in csp
        assert "openstreetmap" not in csp

    def test_csp_allows_the_object_storage_origin_for_blobs(self):
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
        from fastapi.testclient import TestClient

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)
        app.state.storage_origin = "https://bucket.s3.amazonaws.com"

        @app.get("/html")
        async def html_endpoint():
            return HTMLResponse("<html><body>Hello</body></html>")

        csp = TestClient(app).get("/html").headers["Content-Security-Policy"]

        directives = {d.split()[0]: d for d in csp.split("; ")}
        assert "https://bucket.s3.amazonaws.com" in directives["img-src"]
        assert "https://bucket.s3.amazonaws.com" in directives["media-src"]

    def test_csp_has_no_storage_origin_for_local_storage(self):
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
        from fastapi.testclient import TestClient

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/html")
        async def html_endpoint():
            return HTMLResponse("<html><body>Hello</body></html>")

        csp = TestClient(app).get("/html").headers["Content-Security-Policy"]

        assert "media-src 'self' data:" in csp
        assert "amazonaws" not in csp

    def test_allowed_tile_domains_uses_custom_when_set(self):
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
        from fastapi.testclient import TestClient

        from core.middleware import SecurityHeadersMiddleware

        custom_domains = ["https://*.custom-tiles.example.com"]

        app = FastAPI()
        app.state.allowed_tile_domains = custom_domains
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/html")
        async def html_endpoint():
            return HTMLResponse("<html><body>Hello</body></html>")

        client = TestClient(app)
        response = client.get("/html")

        csp = response.headers["Content-Security-Policy"]
        assert "https://*.custom-tiles.example.com" in csp

    def test_connect_src_default_when_not_set(self):
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
        from fastapi.testclient import TestClient

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/html")
        async def html_endpoint():
            return HTMLResponse("<html><body>Hello</body></html>")

        client = TestClient(app)

        with patch("core.middleware.core_config.settings.CSP_ADDITIONAL_CONNECT_SRC", []):
            response = client.get("/html")

        csp = response.headers["Content-Security-Policy"]
        assert "connect-src 'self' https://cdn.jsdelivr.net https://api.github.com;" in csp

    def test_connect_src_includes_additional_origins_when_set(self):
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
        from fastapi.testclient import TestClient

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/html")
        async def html_endpoint():
            return HTMLResponse("<html><body>Hello</body></html>")

        client = TestClient(app)

        extra = ["https://auth.example.com", "https://proxy.example.com"]
        with patch("core.middleware.core_config.settings.CSP_ADDITIONAL_CONNECT_SRC", extra):
            response = client.get("/html")

        csp = response.headers["Content-Security-Policy"]
        assert (
            "connect-src 'self' https://cdn.jsdelivr.net https://api.github.com https://auth.example.com https://proxy.example.com;"
            in csp
        )


class TestAllowedTileDomainsRefresh:
    """Each process re-reads the CSP tile domains, so an edit made elsewhere reaches it."""

    @staticmethod
    def _client(read_at, loader=None):
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse
        from fastapi.testclient import TestClient

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.state.allowed_tile_domains = ["https://*.old.example.com"]
        if read_at is not None:
            app.state.allowed_tile_domains_read_at = read_at
        if loader is not None:
            app.state.allowed_tile_domains_loader = loader
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/html")
        async def html_endpoint():
            return HTMLResponse("<html></html>")

        return TestClient(app)

    def test_a_stale_value_is_re_read_off_the_response_path(self):
        import time

        with self._client(read_at=-1e9, loader=lambda: ["https://new.example.com"]) as client:
            first = client.get("/html").headers["Content-Security-Policy"]
            csp = first
            for _ in range(100):
                if "new.example.com" in csp:
                    break
                time.sleep(0.02)
                csp = client.get("/html").headers["Content-Security-Policy"]

        assert "old.example.com" in first
        assert "https://new.example.com" in csp
        assert "old.example.com" not in csp

    def test_a_fresh_value_is_not_re_read(self):
        import time
        from unittest.mock import MagicMock

        loader = MagicMock()
        csp = self._client(read_at=time.monotonic(), loader=loader).get("/html").headers["Content-Security-Policy"]

        loader.assert_not_called()
        assert "old.example.com" in csp

    def test_a_failed_read_keeps_the_previous_value(self):
        from unittest.mock import MagicMock

        loader = MagicMock(side_effect=RuntimeError("db down"))
        with self._client(read_at=-1e9, loader=loader) as client:
            client.get("/html")
            response = client.get("/html")

        assert response.status_code == 200
        assert "old.example.com" in response.headers["Content-Security-Policy"]

    def test_an_app_without_a_loader_is_left_alone(self):
        csp = self._client(read_at=-1e9).get("/html").headers["Content-Security-Policy"]

        assert "old.example.com" in csp


class TestCookieRouteRefusalIsAProblemDocument:
    """The origin refusal is a problem document and sits inside CORS and the security headers."""

    def _app(self) -> FastAPI:
        from fastapi.middleware.cors import CORSMiddleware

        from core.middleware import SecurityHeadersMiddleware

        app = FastAPI()
        app.state.cors_allow_origins = [ALLOWED_ORIGIN]
        # Added in the order create_app adds them: the origin check innermost, CORS and security headers outside it.
        app.add_middleware(CookieRouteOriginMiddleware)
        app.add_middleware(CORSMiddleware, allow_origins=[ALLOWED_ORIGIN], allow_credentials=True)
        app.add_middleware(SecurityHeadersMiddleware)

        @app.post(REFRESH_PATH)
        async def refresh():
            return {"ok": True}

        return app

    def test_refusal_carries_the_security_headers(self):
        response = TestClient(self._app()).post(REFRESH_PATH, headers={**WEB, "Origin": "https://evil.example"})

        assert response.status_code == 403
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "access-control-allow-origin" not in response.headers

    def test_create_app_adds_the_origin_check_before_cors_and_security_headers(self):
        from pathlib import Path

        main_source = (Path(__file__).resolve().parents[2] / "app" / "main.py").read_text()
        source = main_source[main_source.index("def create_app") :]

        check = source.index("CookieRouteOriginMiddleware")
        assert check < source.index("CORSMiddleware")
        assert check < source.index("SecurityHeadersMiddleware")
