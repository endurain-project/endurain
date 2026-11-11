"""Tests for ``GET /sync``: the page shape, the problem types and the parameters it passes on."""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.dependencies as auth_dependencies
import modules.sync.router as sync_router
import modules.sync.schema as sync_schema

_SYNC = "modules.sync.service.sync"


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(sync_router.router, prefix="/sync")
    core_exceptions.register_exception_handlers(app)
    app.dependency_overrides[auth_dependencies.check_scopes] = lambda: None
    app.dependency_overrides[auth_dependencies.get_current_user_id] = lambda: 7
    app.dependency_overrides[auth_dependencies.get_current_scopes] = lambda: frozenset({"health:read"})
    app.dependency_overrides[core_database.get_db] = lambda: MagicMock()
    return TestClient(app)


def test_the_page_and_the_parameters_reach_the_service():
    page = sync_schema.SyncPage(changes=[], next_cursor="next", has_more=False)
    with patch(_SYNC, return_value=page) as sync:
        response = _client().get("/sync", params=[("cursor", "c"), ("types", "health_weight"), ("types", "gear")])

    assert response.status_code == 200
    assert response.json() == {"changes": [], "next_cursor": "next", "has_more": False}
    args, kwargs = sync.call_args
    assert args[:2] == (7, frozenset({"health:read"}))
    assert kwargs["cursor"] == "c"
    assert kwargs["types"] == [sync_schema.SyncType.HEALTH_WEIGHT, sync_schema.SyncType.GEAR]
    assert kwargs["num_records"] == 100


def test_an_expired_cursor_is_410_sync_expired():
    with patch(_SYNC, side_effect=core_exceptions.SyncExpiredError()):
        response = _client().get("/sync", params={"cursor": "old"})

    assert response.status_code == 410
    assert response.json()["type"] == "urn:endurain:error:sync-expired"


def test_an_unknown_type_and_an_oversized_page_are_refused():
    client = _client()

    assert client.get("/sync", params={"types": "nope"}).status_code == 422
    assert client.get("/sync", params={"num_records": 5000}).status_code == 422
