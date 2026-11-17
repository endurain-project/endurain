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


def test_a_cookie_under_the_plain_name_is_not_read_when_the_name_is_prefixed():
    """The prefix is what stops a cookie planted from a sibling subdomain, so the plain name is ignored."""
    client = _client()
    client.cookies.set("endurain_device", _DEVICE_ID)

    expected = _DEVICE_ID if known_devices_dependencies.DEVICE_COOKIE_NAME == "endurain_device" else None
    assert client.get("/api/v1/auth/probe").json()["device_id"] == expected


def _read_header(header: str | None, cookie: str | None = None) -> str | None:
    client = _client()
    if cookie is not None:
        client.cookies.set(known_devices_dependencies.DEVICE_COOKIE_NAME, cookie)
    headers = {} if header is None else {"X-Device-Id": header}
    return client.get("/api/v1/auth/probe", headers=headers).json()["device_id"]


def test_a_well_formed_mobile_header_is_read():
    assert _read_header(_DEVICE_ID) == _DEVICE_ID


def test_a_malformed_mobile_header_reads_as_none():
    for malformed in ("short", _DEVICE_ID + "x", _DEVICE_ID[:-1] + "=", _DEVICE_ID[:-1] + "/"):
        assert _read_header(malformed) is None, malformed


def test_the_header_wins_over_the_cookie():
    assert _read_header(_DEVICE_ID, cookie="o" * 43) == _DEVICE_ID


def test_the_cookie_is_strict_http_only_and_lasts_400_days():
    response = Response()

    known_devices_dependencies.set_device_cookie(response, _DEVICE_ID)

    header = response.headers["set-cookie"]
    assert header.startswith(f"{known_devices_dependencies.DEVICE_COOKIE_NAME}={_DEVICE_ID};")
    assert "HttpOnly" in header
    assert "SameSite=strict" in header
    assert "Max-Age=34560000" in header
    assert "Path=/;" in header or header.endswith("Path=/")
    assert "Domain" not in header


def test_the_cookie_is_secure_when_deployed():
    with patch.object(known_devices_dependencies.core_config.settings, "ENVIRONMENT", "production"):
        response = Response()
        known_devices_dependencies.set_device_cookie(response, _DEVICE_ID)

    header = response.headers["set-cookie"]
    assert header.startswith("__Host-endurain_device=")
    assert "Secure" in header.removeprefix("__Host-")
    assert "Path=/;" in header or header.endswith("Path=/")
    assert "Domain" not in header


def test_the_cookie_is_not_secure_in_development():
    with patch.object(known_devices_dependencies.core_config.settings, "ENVIRONMENT", "development"):
        response = Response()
        known_devices_dependencies.set_device_cookie(response, _DEVICE_ID)

    assert response.headers["set-cookie"].startswith("endurain_device=")
    assert "Secure" not in response.headers["set-cookie"]
