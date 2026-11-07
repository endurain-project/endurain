"""A health record is edited only by a client that names the version it read."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.database as core_db
import core.exceptions as core_exceptions
import modules.auth.dependencies as auth_deps
import modules.health.health_fasting.router as fasting_router
import modules.health.health_poop.router as poop_router
import modules.health.health_sleep.router as sleep_router
import modules.health.health_steps.router as steps_router
import modules.health.health_water.router as water_router
import modules.health.health_weight.router as weight_router

_HEADERS = {"Authorization": "Bearer x"}

_ROUTES = [
    pytest.param(weight_router, "weight", id="weight"),
    pytest.param(water_router, "water", id="water"),
    pytest.param(steps_router, "steps", id="steps"),
    pytest.param(sleep_router, "sleep", id="sleep"),
    pytest.param(poop_router, "poop", id="poop"),
    pytest.param(fasting_router, "fasting", id="fasting"),
]


def _client(router_module) -> TestClient:
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(router_module.router, prefix="/health")
    app.dependency_overrides[auth_deps.check_scopes] = lambda: None
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: 1
    app.dependency_overrides[core_db.get_db] = lambda: MagicMock()
    return TestClient(app)


@pytest.mark.parametrize(("router_module", "name"), _ROUTES)
def test_an_edit_without_if_match_is_428(router_module, name):
    with patch.object(router_module, f"health_{name}_service") as service:
        response = _client(router_module).patch("/health/1", json={}, headers=_HEADERS)

    assert response.status_code == 428
    getattr(service, f"edit_health_{name}").assert_not_called()


def test_completing_a_fast_without_if_match_is_428():
    with patch.object(fasting_router, "health_fasting_service") as service:
        response = _client(fasting_router).post(
            "/health/1/complete", json={"fast_end_time": "2024-01-16T08:00:00Z"}, headers=_HEADERS
        )

    assert response.status_code == 428
    service.complete_health_fasting.assert_not_called()


@pytest.mark.parametrize(("router_module", "name"), _ROUTES)
def test_a_delete_without_if_match_is_428(router_module, name):
    with patch.object(router_module, f"health_{name}_service") as service:
        response = _client(router_module).delete("/health/1", headers=_HEADERS)

    assert response.status_code == 428
    getattr(service, f"delete_health_{name}").assert_not_called()


@pytest.mark.parametrize(("router_module", "name"), _ROUTES)
def test_a_delete_of_a_stale_version_is_412(router_module, name):
    with patch.object(router_module, f"health_{name}_service") as service:
        getattr(service, f"delete_health_{name}").side_effect = core_exceptions.PreconditionFailedError("stale")
        response = _client(router_module).delete("/health/1", headers={**_HEADERS, "If-Match": '"1"'})

    assert response.status_code == 412


@pytest.mark.parametrize(("router_module", "name"), _ROUTES)
def test_a_delete_with_if_match_is_204_and_hands_the_header_to_the_service(router_module, name):
    with patch.object(router_module, f"health_{name}_service") as service:
        response = _client(router_module).delete("/health/1", headers={**_HEADERS, "If-Match": '"3"'})

    assert response.status_code == 204
    getattr(service, f"delete_health_{name}").assert_called_once()
    assert getattr(service, f"delete_health_{name}").call_args.kwargs == {"if_match": '"3"'}
