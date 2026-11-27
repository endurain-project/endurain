"""Tests for core.middleware_request_id — request ID context and middleware."""

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient


class TestGetRequestId:
    """Tests for get_request_id context function."""

    def test_returns_empty_string_outside_request_context(self):
        from core.middleware_request_id import get_request_id

        result = get_request_id()
        assert result == ""

    def test_returns_set_value_within_context(self):
        from core.middleware_request_id import get_request_id, request_id_ctx

        token = request_id_ctx.set("my-request-id")
        try:
            result = get_request_id()
            assert result == "my-request-id"
        finally:
            request_id_ctx.reset(token)


class TestRequestIdMiddleware:
    """Tests for RequestIdMiddleware using Starlette TestClient."""

    def _make_app(self):
        from core.middleware_request_id import RequestIdMiddleware

        async def handler(request):
            return PlainTextResponse("OK")

        app = Starlette(routes=[Route("/", handler)])
        app.add_middleware(RequestIdMiddleware)
        return app

    def test_with_x_request_id_header_uses_provided_id(self):
        client = TestClient(self._make_app())
        response = client.get("/", headers={"X-Request-ID": "client-provided-id-123"})

        assert response.headers.get("X-Request-ID") == "client-provided-id-123"

    def test_without_header_generates_uuid(self):
        import uuid

        client = TestClient(self._make_app())
        response = client.get("/")

        rid = response.headers.get("X-Request-ID")
        assert rid is not None
        # Verify it's a valid UUID4
        uuid.UUID(rid, version=4)

    def test_with_invalid_header_generates_new_uuid(self):
        import uuid

        client = TestClient(self._make_app())
        response = client.get("/", headers={"X-Request-ID": "invalid header value!!!  "})

        rid = response.headers.get("X-Request-ID")
        assert rid is not None
        uuid.UUID(rid, version=4)
        assert rid != "invalid header value!!!  "

    def test_response_header_contains_request_id(self):
        client = TestClient(self._make_app())
        response = client.get("/", headers={"X-Request-ID": "echo-test-id"})

        assert response.headers.get("X-Request-ID") == "echo-test-id"


class TestUnhandledErrorCarriesRequestId:
    """An unhandled error is answered outside the middleware, yet still names the request."""

    def _client(self):
        from fastapi import FastAPI

        import core.exceptions as core_exceptions
        from core.middleware_request_id import RequestIdMiddleware

        app = FastAPI()
        core_exceptions.register_exception_handlers(app)

        @app.get("/boom")
        def boom():
            raise RuntimeError("boom")

        app.add_middleware(RequestIdMiddleware)
        return TestClient(app, raise_server_exceptions=False)

    def test_the_problem_document_and_header_carry_the_request_id(self):
        response = self._client().get("/boom", headers={"X-Request-ID": "trace-me-1"})

        assert response.status_code == 500
        assert response.json()["request_id"] == "trace-me-1"
        assert response.headers.get("X-Request-ID") == "trace-me-1"
