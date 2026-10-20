from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.database as core_db
import core.dependencies as core_deps
import core.exceptions as core_exceptions
import modules.auth.dependencies as auth_deps
import modules.gears.gear.router as router
import modules.gears.gear.schema as schema

_HEADERS = {"Authorization": "Bearer x"}


@pytest.fixture
def client(mock_db):
    app = FastAPI()
    app.include_router(router.router, prefix="/gears")
    core_exceptions.register_exception_handlers(app)
    app.dependency_overrides[auth_deps.check_scopes] = lambda: None
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: 1
    app.dependency_overrides[core_deps.validate_pagination_values_on_query] = lambda: None
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return TestClient(app)


def _read(**overrides) -> schema.GearRead:
    return schema.GearRead(**{"id": 1, "user_id": 1, "nickname": "Bike", "gear_type": 1, **overrides})


class TestList:
    @patch("modules.gears.gear.service.list_gears")
    def test_passes_the_query_to_the_service(self, mock_list, client, mock_db):
        mock_list.return_value = schema.GearsListResponse(total=1, num_records=5, page_number=2, records=[_read()])

        response = client.get("/gears?page_number=2&num_records=5&show_inactive=false", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json()["total"] == 1
        mock_list.assert_called_once_with(1, mock_db, page_number=2, num_records=5, show_inactive=False)


class TestReadById:
    @patch("modules.gears.gear.service.read_gear_detail")
    def test_unknown_gear_reads_as_null(self, mock_detail, client):
        mock_detail.return_value = None

        response = client.get("/gears/id/999", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json() is None

    def test_a_non_positive_id_is_rejected(self, client):
        assert client.get("/gears/id/0", headers=_HEADERS).status_code == 422


class TestNicknameAndType:
    @patch("modules.gears.gear.service.list_gears_containing_nickname")
    def test_contains(self, mock_list, client):
        mock_list.return_value = [_read(nickname="Mountain Bike")]

        response = client.get("/gears/nickname/contains/Mountain", headers=_HEADERS)

        assert [g["nickname"] for g in response.json()] == ["Mountain Bike"]

    @patch("modules.gears.gear.service.read_gear_by_nickname")
    def test_exact_miss_reads_as_null(self, mock_read, client):
        mock_read.return_value = None

        assert client.get("/gears/nickname/Unknown", headers=_HEADERS).json() is None

    @patch("modules.gears.gear.service.list_gears_by_type")
    def test_type(self, mock_list, client, mock_db):
        mock_list.return_value = [_read()]

        response = client.get("/gears/type/1", headers=_HEADERS)

        assert response.status_code == 200
        mock_list.assert_called_once_with(1, schema.GearType.BIKE, mock_db)

    def test_an_unknown_type_is_rejected(self, client):
        assert client.get("/gears/type/99", headers=_HEADERS).status_code == 422


class TestWrites:
    @patch("modules.gears.gear.service.create_gear")
    def test_create(self, mock_create, client):
        mock_create.return_value = _read(nickname="New Bike")

        response = client.post("/gears", json={"nickname": "New Bike", "gear_type": 1}, headers=_HEADERS)

        assert response.status_code == 201

    @patch("modules.gears.gear.service.create_gear")
    def test_create_conflict_is_409(self, mock_create, client):
        mock_create.side_effect = core_exceptions.ConflictError("exists")

        response = client.post("/gears", json={"nickname": "New Bike", "gear_type": 1}, headers=_HEADERS)

        assert response.status_code == 409

    @patch("modules.gears.gear.service.edit_gear")
    def test_edit(self, mock_edit, client):
        mock_edit.return_value = _read(nickname="Updated")

        response = client.put("/gears", json={"id": 1, "nickname": "Updated", "gear_type": 1}, headers=_HEADERS)

        assert response.status_code == 200
        assert response.json()["nickname"] == "Updated"

    @patch("modules.gears.gear.service.delete_gear")
    def test_delete(self, mock_delete, client, mock_db):
        response = client.delete("/gears/1", headers=_HEADERS)

        assert response.status_code == 204
        mock_delete.assert_called_once_with(1, 1, mock_db)

    @patch("modules.gears.gear.service.delete_gear")
    def test_delete_of_a_missing_gear_is_404(self, mock_delete, client):
        mock_delete.side_effect = core_exceptions.NotFoundError("Gear not found")

        assert client.delete("/gears/1", headers=_HEADERS).status_code == 404
