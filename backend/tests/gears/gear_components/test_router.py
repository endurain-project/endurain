from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.database as core_db
import core.exceptions as core_exceptions
import modules.auth.dependencies as auth_deps
import modules.gears.gear_components.router as router
import modules.gears.gear_components.schema as schema

_HEADERS = {"Authorization": "Bearer x"}
_BODY = {"gear_id": 1, "type": "chain", "brand": "Shimano", "model": "XT"}


@pytest.fixture
def client(mock_db):
    app = FastAPI()
    app.include_router(router.router, prefix="/gear_components")
    core_exceptions.register_exception_handlers(app)
    app.dependency_overrides[auth_deps.check_scopes] = lambda: None
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: 1
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return TestClient(app)


def _read(**overrides) -> schema.GearComponentRead:
    return schema.GearComponentRead(**{"id": 1, "user_id": 1, **_BODY, **overrides})


def test_types_lists_every_gear_type(client):
    response = client.get("/gear_components/types", headers=_HEADERS)

    assert response.status_code == 200
    assert set(response.json()) == {"bike", "shoes", "racquet", "windsurf"}


@patch("modules.gears.gear_components.service.list_gear_components")
def test_list(mock_list, client):
    mock_list.return_value = [_read()]

    assert client.get("/gear_components", headers=_HEADERS).json()[0]["id"] == 1


@patch("modules.gears.gear_components.service.list_components_for_gear")
def test_list_for_gear_passes_the_active_filter(mock_list, client, mock_db):
    mock_list.return_value = [_read(current_distance=3.0)]

    response = client.get("/gear_components/gear_id/1?active=true", headers=_HEADERS)

    assert response.json()[0]["current_distance"] == 3.0
    mock_list.assert_called_once_with(1, 1, mock_db, active=True)


def test_a_non_positive_gear_id_is_rejected(client):
    assert client.get("/gear_components/gear_id/0", headers=_HEADERS).status_code == 422


@patch("modules.gears.gear_components.service.create_gear_component")
def test_create(mock_create, client):
    mock_create.return_value = _read()

    assert client.post("/gear_components", json=_BODY, headers=_HEADERS).status_code == 201


@pytest.mark.parametrize(
    ("error", "status_code"),
    [(core_exceptions.NotFoundError("Gear not found"), 404), (core_exceptions.InvalidInputError("bad type"), 400)],
)
@patch("modules.gears.gear_components.service.create_gear_component")
def test_create_maps_domain_errors(mock_create, error, status_code, client):
    mock_create.side_effect = error

    assert client.post("/gear_components", json=_BODY, headers=_HEADERS).status_code == status_code


@patch("modules.gears.gear_components.service.edit_gear_component")
def test_edit(mock_edit, client):
    mock_edit.return_value = _read(brand="SRAM")

    response = client.put("/gear_components", json={"id": 1, **_BODY, "brand": "SRAM"}, headers=_HEADERS)

    assert response.json()["brand"] == "SRAM"


@patch("modules.gears.gear_components.service.edit_gear_component")
def test_edit_clearing_the_purchase_date_is_rejected(mock_edit, client):
    response = client.put("/gear_components", json={"id": 1, **_BODY, "purchase_date": None}, headers=_HEADERS)

    assert response.status_code == 422
    mock_edit.assert_not_called()


@patch("modules.gears.gear_components.service.delete_gear_component")
def test_delete(mock_delete, client, mock_db):
    response = client.delete("/gear_components/4", headers=_HEADERS)

    assert response.status_code == 204
    mock_delete.assert_called_once_with(1, 4, mock_db)
