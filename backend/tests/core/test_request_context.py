"""Tests for core.request_context — the request published for code with no request parameter."""

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from core.request_context import RequestContextMiddleware, get_current_request


class TestRequestContextMiddleware:
    def test_publishes_the_request_to_the_route_and_its_threads(self):
        seen = {}

        def handler(request):
            # A synchronous route runs in the thread pool, as FastAPI's sync routes and dependencies do.
            current = get_current_request()
            seen["path"] = current.url.path if current else None
            request.state.marker = "set by the route"
            seen["marker"] = getattr(current.state, "marker", None) if current else None
            return PlainTextResponse("OK")

        app = Starlette(routes=[Route("/audited", handler)])
        app.add_middleware(RequestContextMiddleware)

        response = TestClient(app).get("/audited")

        assert response.status_code == 200
        assert seen["path"] == "/audited"
        # Request objects built for the same scope share their state, so a dependency's cache is visible.
        assert seen["marker"] == "set by the route"

    def test_nothing_is_published_outside_a_request(self):
        assert get_current_request() is None
