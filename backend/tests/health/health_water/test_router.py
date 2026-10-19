from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import core.dependencies as core_deps
    import modules.auth.dependencies as auth_deps
    import modules.health.health_water.router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/health_water")

    def _mock():
        return None

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = _uid
    app.dependency_overrides[core_deps.validate_pagination_values_on_query] = _mock
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadHealthWaterAllPagination:
    @patch("modules.health.health_water.router.health_water_crud.get_health_water_number_by_user_id")
    @patch("modules.health.health_water.router.health_water_crud.get_health_water_by_user_id")
    def test_list_success(self, mock_get, mock_get_number, mock_db):
        from modules.health.health_water.schema import HealthWaterRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [HealthWaterRead(id=1, user_id=1)]
        mock_get_number.return_value = 1

        response = client.get("/health_water", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    @patch("modules.health.health_water.router.health_water_crud.get_health_water_number_by_user_id")
    @patch("modules.health.health_water.router.health_water_crud.get_health_water_by_user_id")
    def test_list_empty(self, mock_get, mock_get_number, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = []
        mock_get_number.return_value = 0

        response = client.get("/health_water", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["records"] == []


class TestCreateHealthWater:
    @patch("modules.health.health_water.router.health_water_crud.create_health_water")
    @patch("modules.health.health_water.router.health_water_crud.get_health_water_by_date_and_user_id")
    def test_create_new(self, mock_get_by_date, mock_create, mock_db):
        from modules.health.health_water.schema import HealthWaterRead

        client = TestClient(_build_app(mock_db))
        mock_get_by_date.return_value = None
        mock_create.return_value = HealthWaterRead(id=1, user_id=1, amount_ml=500.0)

        response = client.post(
            "/health_water",
            json={"amount_ml": 500, "date": "2024-01-15"},
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 201

    @patch("modules.health.health_water.router.health_water_crud.edit_health_water")
    @patch("modules.health.health_water.router.health_water_crud.get_health_water_by_date_and_user_id")
    def test_create_accumulates(self, mock_get_by_date, mock_edit, mock_db):
        from modules.health.health_water.schema import HealthWaterRead

        client = TestClient(_build_app(mock_db))
        existing = HealthWaterRead(id=1, user_id=1, amount_ml=300.0)
        mock_get_by_date.return_value = existing
        mock_edit.return_value = HealthWaterRead(id=1, user_id=1, amount_ml=800.0)

        response = client.post(
            "/health_water",
            json={"amount_ml": 500, "date": "2024-01-15"},
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 201


class TestEditHealthWater:
    @patch("modules.health.health_water.router.health_water_crud.edit_health_water")
    def test_edit_success(self, mock_edit, mock_db):
        from modules.health.health_water.schema import HealthWaterRead

        client = TestClient(_build_app(mock_db))
        mock_edit.return_value = HealthWaterRead(id=1, user_id=1, amount_ml=750.0)

        response = client.put(
            "/health_water",
            json={"id": 1, "user_id": 1, "amount_ml": 750},
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 200


class TestDeleteHealthWater:
    @patch("modules.health.health_water.router.health_water_crud.delete_health_water")
    def test_delete_success(self, mock_delete, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.delete("/health_water/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 204
