"""Tests for the server-log read route: it pages like every cursor feed."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions
import modules.auth.dependencies as auth_dependencies
import modules.server_settings.logs_router as logs_router
import modules.server_settings.logs_schema as logs_schema

_SERVICE = "modules.server_settings.logs_router.logs_service.read_logs"


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(logs_router.router, prefix="/server-settings/logs")
    core_exceptions.register_exception_handlers(app)
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    return TestClient(app)


def _page() -> logs_schema.LogPage:
    entry = logs_schema.LogEntry(
        timestamp=None, level="INFO", logger=None, message="m", request_id=None, context=None, exception=None
    )
    return logs_schema.LogPage(items=[entry], num_records=50, next_cursor="120")


def test_the_page_uses_the_cursor_page_names(client):
    with patch(_SERVICE, return_value=_page()) as read:
        response = client.get("/server-settings/logs?num_records=50&cursor=77&level=WARNING")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "num_records", "next_cursor"}
    assert body["next_cursor"] == "120"
    assert read.call_args.args == (50, logs_schema.LogLevel.WARNING, None, 77)


def test_the_text_filter_is_message_contains(client):
    with patch(_SERVICE, return_value=_page()) as read:
        client.get("/server-settings/logs?message_contains=strava")

    assert read.call_args.args == (200, None, "strava", None)


@pytest.mark.parametrize("query", ["after=3", "limit=5", "search=strava"])
def test_the_old_names_are_ignored(client, query):
    with patch(_SERVICE, return_value=_page()) as read:
        client.get(f"/server-settings/logs?{query}")

    assert read.call_args.args == (200, None, None, None)


@pytest.mark.parametrize("cursor", ["abc", "-1", "1" * 19])
def test_a_cursor_that_is_not_a_position_is_refused(client, cursor):
    with patch(_SERVICE, return_value=_page()):
        assert client.get(f"/server-settings/logs?cursor={cursor}").status_code == 422
