"""Responses are gzip-compressed for clients that accept it, and still carry every header."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.testclient import TestClient

import core.middleware as core_middleware
import core.middleware_request_id as core_middleware_request_id

_BIG = {"waypoints": [{"lat": 38.7223, "lon": -9.1393, "t": index} for index in range(500)]}


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """A one-route app wired as ``create_app`` wires it: request id first, compression outermost."""
    asset = tmp_path / "bundle.js"
    asset.write_text("console.log('endurain');\n" * 500)
    app = FastAPI()

    @app.get("/big")
    def big() -> dict:
        return _BIG

    @app.get("/small")
    def small() -> dict:
        return {"ok": True}

    @app.get("/asset")
    def asset_route() -> FileResponse:
        return FileResponse(asset, media_type="text/javascript")

    app.add_middleware(core_middleware_request_id.RequestIdMiddleware)
    core_middleware.install_compression(app)
    return TestClient(app)


class TestCompression:
    def test_a_large_response_is_gzipped_for_a_client_that_accepts_it(self, client):
        response = client.get("/big", headers={"Accept-Encoding": "gzip"})

        assert response.headers["Content-Encoding"] == "gzip"
        assert response.headers["Vary"] == "Accept-Encoding"
        assert response.json() == _BIG
        assert response.num_bytes_downloaded < len(str(_BIG)) // 3

    def test_the_same_response_is_plain_for_a_client_that_does_not(self, client):
        response = client.get("/big", headers={"Accept-Encoding": "identity"})

        assert "Content-Encoding" not in response.headers
        assert response.json() == _BIG

    def test_a_small_response_still_reads_correctly(self, client):
        response = client.get("/small", headers={"Accept-Encoding": "gzip"})

        assert response.json() == {"ok": True}

    def test_a_served_asset_is_gzipped(self, client):
        response = client.get("/asset", headers={"Accept-Encoding": "gzip"})

        assert response.headers["Content-Encoding"] == "gzip"
        assert response.text.startswith("console.log('endurain');")

    def test_the_request_id_survives_compression(self, client):
        response = client.get("/big", headers={"Accept-Encoding": "gzip"})

        assert response.headers["X-Request-ID"]

    def test_a_response_that_is_already_encoded_is_not_compressed_again(self):
        app = FastAPI()

        @app.get("/encoded")
        def encoded():
            from fastapi import Response

            return Response(b"x" * 5000, headers={"Content-Encoding": "br"})

        core_middleware.install_compression(app)

        response = TestClient(app).get("/encoded", headers={"Accept-Encoding": "gzip"})

        assert response.headers["Content-Encoding"] == "br"


class TestWiring:
    def test_the_level_is_moderate_not_the_costly_maximum(self):
        assert core_middleware.COMPRESSION_LEVEL < 9

    def test_create_app_installs_compression_after_every_other_middleware(self):
        """Added last means outermost, so every header the inner layers add is on the compressed response."""
        # main.py builds the app on import, so the wiring is read from its source.
        main_source = (Path(__file__).resolve().parents[2] / "app" / "main.py").read_text()
        source = main_source[main_source.index("def create_app") :]

        assert source.count("install_compression(") == 1
        assert source.index("install_compression(") > source.index("RequestIdMiddleware")
