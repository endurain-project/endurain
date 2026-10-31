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

    @app.post("/files/{kind}")
    async def upload(kind: str, file: UploadFile):
        return {"kind": kind, "name": file.filename}

    return TestClient(app)


_MULTIPART = {"content-type": "multipart/form-data; boundary=b"}


@pytest.fixture(autouse=True)
def _small_limits(monkeypatch):
    monkeypatch.setattr(body_limit, "MAX_BODY_BYTES", 100)
    monkeypatch.setattr(body_limit, "MAX_UPLOAD_BODY_BYTES", 1000)


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

        @app.post("/late")
        async def late(file: UploadFile):
            return {}

        assert client.post("/late", content=b"x" * 500, headers=_MULTIPART).status_code != 413
