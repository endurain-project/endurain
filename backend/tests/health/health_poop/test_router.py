from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import core.dependencies as core_deps
    import modules.auth.dependencies as auth_deps
    import modules.health.health_poop.router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/health_poop")

    def _mock():
        return None

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = _uid
    app.dependency_overrides[core_deps.validate_pagination_values_on_query] = _mock
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadHealthPoopAllPagination:
    @patch("modules.health.health_poop.router.health_poop_crud.get_health_poop_number_by_user_id")
    @patch("modules.health.health_poop.router.health_poop_crud.get_health_poop_by_user_id")
    def test_list_success(self, mock_get, mock_get_number, mock_db):
        from modules.health.health_poop.schema import HealthPoopRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [HealthPoopRead(id=1, user_id=1)]
        mock_get_number.return_value = 1

        response = client.get("/health_poop", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    @patch("modules.health.health_poop.router.health_poop_crud.get_health_poop_number_by_user_id")
    @patch("modules.health.health_poop.router.health_poop_crud.get_health_poop_by_user_id")
    def test_list_empty(self, mock_get, mock_get_number, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = []
        mock_get_number.return_value = 0

        response = client.get("/health_poop", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["records"] == []


class TestReadHealthPoopById:
    @patch("modules.health.health_poop.router.health_poop_crud.get_health_poop_by_id_and_user_id")
    def test_success(self, mock_get, mock_db):
        from modules.health.health_poop.schema import HealthPoopRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = HealthPoopRead(id=1, user_id=1)

        response = client.get("/health_poop/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200

    @patch("modules.health.health_poop.router.health_poop_crud.get_health_poop_by_id_and_user_id")
    def test_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        response = client.get("/health_poop/999", headers={"Authorization": "Bearer x"})
        assert response.status_code == 404


class TestCreateHealthPoop:
    @patch("modules.health.health_poop.router.health_poop_crud.create_health_poop")
    def test_create_success(self, mock_create, mock_db):
        from modules.health.health_poop.schema import HealthPoopRead

        client = TestClient(_build_app(mock_db))
        mock_create.return_value = HealthPoopRead(id=1, user_id=1)

        response = client.post(
            "/health_poop",
            json={"date_time": "2024-01-15T10:00:00"},
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 201


class TestEditHealthPoop:
    @patch("modules.health.health_poop.router.health_poop_crud.edit_health_poop")
    def test_edit_success(self, mock_edit, mock_db):
        from modules.health.health_poop.schema import HealthPoopRead

        client = TestClient(_build_app(mock_db))
        mock_edit.return_value = HealthPoopRead(id=1, user_id=1)

        response = client.put(
            "/health_poop",
            json={"id": 1, "user_id": 1},
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 200


class TestDeleteHealthPoop:
    @patch("modules.health.health_poop.router.health_poop_crud.delete_health_poop")
    def test_delete_success(self, mock_delete, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.delete("/health_poop/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 204
