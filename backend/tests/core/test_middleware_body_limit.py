"""Tests for the request body size cap."""

import pytest
from fastapi import FastAPI, Request, UploadFile
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions
import core.middleware_body_limit as body_limit


@pytest.fixture
def client():
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.add_middleware(body_limit.BodySizeLimitMiddleware)

    @app.post("/echo")
    async def echo(request: Request):
        return {"size": len(await request.body())}

    @app.post("/json")
    async def json_route(request: Request):
        return {"size": len(await request.body())}

    @app.post("/files/{kind}", openapi_extra={body_limit.BODY_LIMIT_EXTENSION: 1000})
    async def upload(kind: str, file: UploadFile):
        return {"kind": kind, "name": file.filename}

    @app.post("/api/v1/auth/echo")
    @app.post("/api/v1/public/echo")
    async def credential_echo(request: Request):
        return {"size": len(await request.body())}

    @app.post("/api/v1/public/files", openapi_extra={body_limit.BODY_LIMIT_EXTENSION: 1000})
    async def public_upload(file: UploadFile):
        return {"name": file.filename}

    return TestClient(app)


_MULTIPART = {"content-type": "multipart/form-data; boundary=b"}


@pytest.fixture(autouse=True)
def _small_limits(monkeypatch):
    monkeypatch.setattr(body_limit, "MAX_BODY_BYTES", 100)
    monkeypatch.setattr(body_limit, "MAX_PUBLIC_BODY_BYTES", 50)


class TestDeclaredLength:
    def test_a_body_within_the_limit_passes(self, client):
        assert client.post("/echo", content=b"x" * 100).json() == {"size": 100}

    def test_a_declared_length_over_the_limit_is_refused_before_it_is_read(self, client):
        response = client.post("/echo", content=b"x" * 101)

        assert response.status_code == 413
        assert response.headers["content-type"].startswith("application/problem+json")

    def test_an_upload_may_be_larger_than_a_plain_body(self, client):
        response = client.post("/files/photo", content=b"x" * 500, headers=_MULTIPART)

        assert response.status_code != 413

    def test_an_upload_has_a_limit_too(self, client):
        response = client.post("/files/photo", content=b"x" * 1001, headers=_MULTIPART)

        assert response.status_code == 413


class TestStreamedBody:
    def test_a_body_with_no_declared_length_is_cut_off_at_the_limit(self, client):
        def chunks():
            for _ in range(5):
                yield b"x" * 40

        response = client.post("/echo", content=chunks())

        assert response.status_code == 413

    def test_a_streamed_body_within_the_limit_passes(self, client):
        def chunks():
            yield b"x" * 40
            yield b"x" * 40

        assert client.post("/echo", content=chunks()).json() == {"size": 80}


class TestOnlyUploadRoutesGetTheLargeLimit:
    """A multipart content type does not raise the limit on a route that takes no upload."""

    def test_a_multipart_post_to_a_json_route_gets_the_small_limit(self, client):
        assert client.post("/json", content=b"x" * 500, headers=_MULTIPART).status_code == 413

    def test_a_multipart_post_to_an_unknown_path_gets_the_small_limit(self, client):
        assert client.post("/nowhere", content=b"x" * 500, headers=_MULTIPART).status_code == 413

    def test_a_streamed_multipart_body_to_a_non_upload_route_is_cut_off_at_the_small_limit(self, client):
        def chunks():
            for _ in range(5):
                yield b"x" * 40

        assert client.post("/json", content=chunks(), headers=_MULTIPART).status_code == 413

    def test_a_streamed_multipart_body_to_an_upload_route_is_cut_off_at_the_large_limit(self, client):
        head = b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.bin"\r\n\r\n'

        def chunks():
            yield head
            for _ in range(30):
                yield b"x" * 40
            yield b"\r\n--b--\r\n"

        assert client.post("/files/photo", content=chunks(), headers=_MULTIPART).status_code == 413

    def test_a_route_added_after_the_app_was_built_is_picked_up(self, client):
        app = client.app

        @app.post("/late", openapi_extra={body_limit.BODY_LIMIT_EXTENSION: 1000})
        async def late(file: UploadFile):
            return {}

        assert client.post("/late", content=b"x" * 500, headers=_MULTIPART).status_code != 413


class TestCredentialRoutesGetTheSmallestLimit:
    """A request under the auth and public prefixes carries a small body, whatever its content type."""

    @pytest.mark.parametrize("path", ["/api/v1/auth/echo", "/api/v1/public/echo"])
    def test_a_body_within_the_cap_passes(self, client, path):
        assert client.post(path, content=b"x" * 50).json() == {"size": 50}

    @pytest.mark.parametrize("path", ["/api/v1/auth/echo", "/api/v1/public/echo"])
    def test_a_declared_length_over_the_cap_is_refused(self, client, path):
        response = client.post(path, content=b"x" * 51)

        assert response.status_code == 413
        assert response.headers["content-type"].startswith("application/problem+json")

    def test_a_streamed_body_over_the_cap_is_cut_off(self, client):
        def chunks():
            for _ in range(3):
                yield b"x" * 30

        assert client.post("/api/v1/auth/echo", content=chunks()).status_code == 413

    def test_a_multipart_body_to_a_route_with_no_upload_cap_gets_the_cap(self, client):
        assert client.post("/api/v1/auth/echo", content=b"x" * 51, headers=_MULTIPART).status_code == 413

    def test_an_upload_route_under_a_prefix_keeps_its_declared_cap(self, client):
        assert client.post("/api/v1/public/files", content=b"x" * 500, headers=_MULTIPART).status_code != 413
        assert client.post("/api/v1/public/files", content=b"x" * 1001, headers=_MULTIPART).status_code == 413

    def test_a_path_outside_the_prefixes_keeps_the_general_cap(self, client):
        assert client.post("/echo", content=b"x" * 100).json() == {"size": 100}

    def test_a_path_that_only_starts_like_a_prefix_keeps_the_general_cap(self, client):
        assert client.post("/api/v1/authors", content=b"x" * 100).status_code != 413


@pytest.fixture
def real_client():
    """The production API router behind the middleware, so the real upload routes are matched."""
    import core.problem_details as core_problem_details
    from api import router as api_router

    app = core_problem_details.ProblemDetailsFastAPI()
    core_exceptions.register_exception_handlers(app)
    app.add_middleware(body_limit.BodySizeLimitMiddleware)
    app.include_router(api_router)
    return TestClient(app)


_IDP_ICON = "/api/v1/identity-providers/6f1c9c0e-3b7a-4c55-9d1e-2f6a8b4d7e10/icon"
_BULK_IMPORT = "/api/v1/activities/bulk-import"
_REAL_BODY = 7 * 1024 * 1024
_ABOVE_IMAGE_CAPS = 25 * 1024 * 1024


class TestEachUploadRouteHasItsOwnLimit:
    """A route's cap is its own largest file plus framing, not the largest upload any route takes."""

    @pytest.mark.parametrize("path", [_IDP_ICON, "/api/v1/server-settings/login-photo"])
    def test_a_declared_length_over_a_small_image_cap_is_refused(self, real_client, path):
        response = real_client.put(path, content=b"x" * _REAL_BODY, headers=_MULTIPART)

        assert response.status_code == 413
        assert response.headers["content-type"].startswith("application/problem+json")

    def test_a_streamed_body_over_a_small_image_cap_is_cut_off(self, real_client):
        def chunks():
            for _ in range(_REAL_BODY // (256 * 1024)):
                yield b"x" * 256 * 1024

        assert real_client.put(_IDP_ICON, content=chunks(), headers=_MULTIPART).status_code == 413

    def test_an_upload_route_with_no_cap_gets_the_small_limit(self, client):
        @client.app.post("/uncapped")
        async def uncapped(file: UploadFile):
            return {}

        assert client.post("/uncapped", content=b"x" * 500, headers=_MULTIPART).status_code == 413

    def test_an_archive_route_accepts_a_body_above_the_image_caps(self, real_client):
        response = real_client.post(_BULK_IMPORT, content=b"x" * _ABOVE_IMAGE_CAPS, headers=_MULTIPART)

        assert response.status_code != 413


_CREDENTIAL_CAP = 64 * 1024
_FORM = {"content-type": "application/x-www-form-urlencoded"}


class TestRealCredentialRoutes:
    """The production routes under the auth and public prefixes carry 64 KiB at most."""

    @pytest.fixture(autouse=True)
    def _production_caps(self, monkeypatch):
        monkeypatch.undo()

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/auth/login",
            "/api/v1/auth/mfa/verify",
            "/api/v1/public/password-reset/request",
            "/api/v1/public/sign-up/request",
            "/api/v1/public/onboarding",
        ],
    )
    def test_a_body_over_the_cap_is_refused(self, real_client, path):
        response = real_client.post(path, content=b"x" * (_CREDENTIAL_CAP + 1), headers=_FORM)

        assert response.status_code == 413

    def test_a_multipart_login_over_the_cap_is_refused(self, real_client):
        response = real_client.post("/api/v1/auth/login", content=b"x" * (_CREDENTIAL_CAP + 1), headers=_MULTIPART)

        assert response.status_code == 413

    def test_a_body_at_the_cap_is_not_refused_for_its_size(self, real_client):
        response = real_client.post("/api/v1/auth/login", content=b"x" * _CREDENTIAL_CAP, headers=_FORM)

        assert response.status_code != 413
