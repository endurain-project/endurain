"""Tests for reading and setting the device cookie."""

from unittest.mock import patch

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

import modules.auth.known_devices.dependencies as known_devices_dependencies

_DEVICE_ID = "AbCd-_" + "x" * 37


def _client() -> TestClient:
    app = FastAPI()

    @app.get("/api/v1/auth/probe")
    def probe(device_id: known_devices_dependencies.DeviceId) -> dict[str, str | None]:
        return {"device_id": device_id}

    return TestClient(app)


def _read(cookie: str | None) -> str | None:
    client = _client()
    if cookie is not None:
        client.cookies.set(known_devices_dependencies.DEVICE_COOKIE_NAME, cookie)
    return client.get("/api/v1/auth/probe").json()["device_id"]


def test_a_well_formed_cookie_is_read():
    assert _read(_DEVICE_ID) == _DEVICE_ID


def test_no_cookie_reads_as_none():
    assert _read(None) is None


def test_a_malformed_cookie_reads_as_none():
    for malformed in ("short", _DEVICE_ID + "x", _DEVICE_ID[:-1] + "=", _DEVICE_ID[:-1] + "/", ""):
        assert _read(malformed) is None, malformed


def test_the_cookie_is_strict_http_only_and_lasts_400_days():
    response = Response()

    known_devices_dependencies.set_device_cookie(response, _DEVICE_ID)

    header = response.headers["set-cookie"]
    assert header.startswith(f"endurain_device={_DEVICE_ID};")
    assert "HttpOnly" in header
    assert "SameSite=strict" in header
    assert "Max-Age=34560000" in header
    assert "Path=/api/v1;" in header or header.endswith("Path=/api/v1")


def test_the_cookie_is_secure_when_deployed():
    with patch.object(known_devices_dependencies.core_config.settings, "ENVIRONMENT", "production"):
        response = Response()
        known_devices_dependencies.set_device_cookie(response, _DEVICE_ID)

    assert "Secure" in response.headers["set-cookie"]


def test_the_cookie_is_not_secure_in_development():
    with patch.object(known_devices_dependencies.core_config.settings, "ENVIRONMENT", "development"):
        response = Response()
        known_devices_dependencies.set_device_cookie(response, _DEVICE_ID)

    assert "Secure" not in response.headers["set-cookie"]
