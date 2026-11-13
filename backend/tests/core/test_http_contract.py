"""The HTTP behaviour every route shares: conditional GET, HEAD, caching, correlation and security headers."""

from collections.abc import Callable

import pytest
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient

import core.etag as core_etag
import core.exceptions as core_exceptions
import core.middleware as core_middleware
import core.middleware_request_id as core_middleware_request_id
import core.router as core_router

_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
_TRACEPARENT = f"00-{_TRACE_ID}-00f067aa0ba902b7-01"


def _semantics_app() -> FastAPI:
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)

    @app.get("/versioned")
    def versioned(response: Response) -> dict[str, int]:
        core_etag.set_etag(response, 7)
        return {"version": 7}

    @app.get("/plain")
    def plain() -> dict[str, int]:
        return {"n": 1}

    @app.get("/own-cache")
    def own_cache(response: Response) -> dict[str, int]:
        response.headers["Cache-Control"] = "no-store"
        return {"n": 1}

    @app.post("/versioned")
    def post_versioned(response: Response) -> dict[str, int]:
        core_etag.set_etag(response, 7)
        return {"version": 7}

    app.add_middleware(core_middleware.GetSemanticsMiddleware)
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_semantics_app())


class TestIfNoneMatch:
    """The ETag is the version for ``If-Match``, not a validator of the body, so it never answers 304."""

    @pytest.mark.parametrize("header", ['"7"', 'W/"7"', "*"])
    def test_a_matching_if_none_match_still_answers_the_body(self, client, header):
        response = client.get("/versioned", headers={"If-None-Match": header})

        assert response.status_code == 200
        assert response.json() == {"version": 7}
        assert response.headers["ETag"] == '"7"'


class TestHead:
    def test_head_on_a_get_route_has_the_headers_and_no_body(self, client):
        get = client.get("/versioned")
        head = client.head("/versioned")

        assert head.status_code == 200
        assert head.content == b""
        assert head.headers["ETag"] == get.headers["ETag"]
        assert head.headers["Content-Length"] == get.headers["Content-Length"]

    def test_head_on_a_post_only_route_is_still_refused(self):
        app = FastAPI()

        @app.post("/only-post")
        def only_post() -> dict[str, bool]:
            return {"ok": True}

        app.add_middleware(core_middleware.GetSemanticsMiddleware)

        assert TestClient(app).head("/only-post").status_code == 405


class TestCacheControl:
    def test_json_without_a_policy_is_private_and_revalidated(self, client):
        assert client.get("/plain").headers["Cache-Control"] == "private, no-cache"

    def test_a_policy_the_route_sets_is_kept(self, client):
        assert client.get("/own-cache").headers["Cache-Control"] == "no-store"

    def test_a_problem_document_is_not_cacheable_either(self, client):
        assert client.get("/missing").headers["Cache-Control"] == "private, no-cache"


class TestCorsHeaders:
    @pytest.mark.parametrize("name", ["X-Request-ID", "traceparent", "tracestate"])
    def test_a_request_header_a_client_sends_is_allowed(self, name):
        assert name in core_middleware.CORS_ALLOW_HEADERS

    @pytest.mark.parametrize("name", ["Retry-After", "Content-Location"])
    def test_a_response_header_a_client_reads_is_exposed(self, name):
        assert name in core_middleware.CORS_EXPOSE_HEADERS


class TestCorrelation:
    @staticmethod
    def _client() -> TestClient:
        app = FastAPI()

        @app.get("/")
        def root() -> dict[str, str]:
            return {"request_id": core_middleware_request_id.get_request_id()}

        app.add_middleware(core_middleware_request_id.RequestIdMiddleware)
        return TestClient(app)

    def test_a_traceparent_is_echoed_and_its_trace_id_is_the_request_id(self):
        response = self._client().get("/", headers={"traceparent": _TRACEPARENT, "tracestate": "vendor=opaque"})

        assert response.headers["traceparent"] == _TRACEPARENT
        assert response.headers["tracestate"] == "vendor=opaque"
        assert response.headers["X-Request-ID"] == _TRACE_ID
        assert response.json() == {"request_id": _TRACE_ID}

    def test_an_explicit_request_id_wins_over_the_trace_id(self):
        response = self._client().get("/", headers={"traceparent": _TRACEPARENT, "X-Request-ID": "abc-123"})

        assert response.headers["X-Request-ID"] == "abc-123"
        assert response.headers["traceparent"] == _TRACEPARENT

    @pytest.mark.parametrize(
        "traceparent",
        [
            "garbage",
            f"ff-{_TRACE_ID}-00f067aa0ba902b7-01",
            f"00-{'0' * 32}-00f067aa0ba902b7-01",
            f"00-{_TRACE_ID}-{'0' * 16}-01",
            f"00-{_TRACE_ID.upper()}-00f067aa0ba902b7-01",
        ],
    )
    def test_an_invalid_traceparent_is_neither_used_nor_echoed(self, traceparent):
        response = self._client().get("/", headers={"traceparent": traceparent, "tracestate": "a=b"})

        assert "traceparent" not in response.headers
        assert "tracestate" not in response.headers
        assert response.headers["X-Request-ID"] != _TRACE_ID

    def test_no_trace_headers_are_invented(self):
        response = self._client().get("/")

        assert "traceparent" not in response.headers


def _stack(*routes: Callable[[], None]) -> FastAPI:
    """The layers ``create_app`` stacks, in its order: semantics innermost, then security headers, then the id.

    Args:
        *routes: Handlers to serve under ``/api/v1/<function name>``, registered before the frontend fallback.
    """
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    for route in routes:
        app.get(f"/api/v1/{route.__name__}")(route)
    app.include_router(core_router.router)
    app.add_middleware(core_middleware.GetSemanticsMiddleware)
    app.add_middleware(core_middleware.SecurityHeadersMiddleware)
    app.add_middleware(core_middleware_request_id.RequestIdMiddleware)
    return app


@pytest.fixture
def full_client() -> TestClient:
    return TestClient(_stack(), raise_server_exceptions=False)


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-site",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


class TestSecurityHeaders:
    def test_a_404_problem_document_carries_them(self, full_client):
        response = full_client.get("/api/v1/does-not-exist")

        assert response.status_code == 404
        assert {name: response.headers[name] for name in _SECURITY_HEADERS} == _SECURITY_HEADERS

    def test_a_429_carries_them(self):
        def limited() -> None:
            raise core_exceptions.TooManyRequestsError("slow down")

        response = TestClient(_stack(limited)).get("/api/v1/limited")

        assert response.status_code == 429
        assert {name: response.headers[name] for name in _SECURITY_HEADERS} == _SECURITY_HEADERS

    def test_an_unhandled_500_carries_them(self):
        def explodes() -> None:
            raise RuntimeError("boom")

        response = TestClient(_stack(explodes), raise_server_exceptions=False).get("/api/v1/explodes")

        assert response.status_code == 500
        assert {name: response.headers[name] for name in _SECURITY_HEADERS} == _SECURITY_HEADERS
        assert response.headers["Content-Type"].startswith("application/problem+json")

    def test_the_html_policy_forbids_framing(self):
        app = FastAPI()
        app.state.allowed_tile_domains = []

        @app.get("/", response_class=HTMLResponse)
        def page() -> str:
            return "<html></html>"

        app.add_middleware(core_middleware.SecurityHeadersMiddleware)
        policy = TestClient(app).get("/").headers["Content-Security-Policy"]

        assert "frame-ancestors 'none'" in policy
        assert policy.startswith("default-src 'self'")


class TestUnknownApiPaths:
    @pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
    def test_an_unknown_api_path_is_a_404_problem_document_for_every_method(self, full_client, method):
        response = full_client.request(method, "/api/v1/nothing/here", headers={"X-Client-Type": "mobile"})

        assert response.status_code == 404
        assert response.headers["Content-Type"].startswith("application/problem+json")

    def test_a_known_path_with_the_wrong_method_is_still_a_405(self, full_client):
        response = full_client.delete("/api/v1/about", headers={"X-Client-Type": "mobile"})

        assert response.status_code == 405
        assert "GET" in response.headers["Allow"]

    def test_head_on_a_get_route_has_no_body(self, full_client):
        response = full_client.head("/api/v1/about")

        assert response.status_code == 200
        assert response.content == b""
