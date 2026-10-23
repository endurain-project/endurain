from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions
from modules.health.health_water.schema import HealthWaterListResponse, HealthWaterRead

_SERVICE = "modules.health.health_water.router.health_water_service"
_HEADERS = {"Authorization": "Bearer x"}


def _build_app(mock_db):
    import core.database as core_db
    import core.dependencies as core_deps
    import modules.auth.dependencies as auth_deps
    import modules.health.health_water.router as router

    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
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
    @patch(f"{_SERVICE}.list_health_water")
    def test_list_success(self, mock_list, mock_db):
        mock_list.return_value = HealthWaterListResponse(total=1, records=[HealthWaterRead(id=1, user_id=1)])

        response = TestClient(_build_app(mock_db)).get("/health_water", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json()["total"] == 1

    @patch(f"{_SERVICE}.list_health_water")
    def test_list_empty(self, mock_list, mock_db):
        mock_list.return_value = HealthWaterListResponse(total=0, records=[])

        response = TestClient(_build_app(mock_db)).get("/health_water", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json()["records"] == []

    @patch(f"{_SERVICE}.list_health_water")
    def test_passes_pagination_and_interval_through(self, mock_list, mock_db):
        mock_list.return_value = HealthWaterListResponse(total=0, records=[])

        TestClient(_build_app(mock_db)).get(
            "/health_water?page_number=2&num_records=10&interval=last_30_days", headers=_HEADERS
        )

        args = mock_list.call_args.args
        assert args[0] == 1
        assert args[2:4] == (2, 10)
        assert args[4].value == "last_30_days"


class TestCreateHealthWater:
    @patch(f"{_SERVICE}.create_health_water")
    def test_create(self, mock_create, mock_db):
        mock_create.return_value = HealthWaterRead(id=1, user_id=1, amount_ml=500.0)

        response = TestClient(_build_app(mock_db)).post(
            "/health_water", json={"amount_ml": 500, "date": "2024-01-15"}, headers=_HEADERS
        )

        assert response.status_code == 201
        assert response.json()["amount_ml"] == 500.0

    @patch(f"{_SERVICE}.create_health_water")
    def test_conflict_is_409(self, mock_create, mock_db):
        mock_create.side_effect = core_exceptions.ConflictError("Duplicate entry error")

        response = TestClient(_build_app(mock_db)).post(
            "/health_water", json={"amount_ml": 500, "date": "2024-01-15"}, headers=_HEADERS
        )

        assert response.status_code == 409


class TestEditHealthWater:
    @patch(f"{_SERVICE}.edit_health_water")
    def test_edit(self, mock_edit, mock_db):
        mock_edit.return_value = HealthWaterRead(id=1, user_id=1, amount_ml=900.0)

        response = TestClient(_build_app(mock_db)).put(
            "/health_water", json={"id": 1, "user_id": 1, "amount_ml": 900}, headers=_HEADERS
        )

        assert response.status_code == 200
        assert response.json()["amount_ml"] == 900.0

    @patch(f"{_SERVICE}.edit_health_water")
    def test_not_found_is_404(self, mock_edit, mock_db):
        mock_edit.side_effect = core_exceptions.NotFoundError("Health water not found")

        response = TestClient(_build_app(mock_db)).put(
            "/health_water", json={"id": 9, "user_id": 1, "amount_ml": 900}, headers=_HEADERS
        )

        assert response.status_code == 404

    @patch(f"{_SERVICE}.edit_health_water")
    def test_another_users_record_is_403(self, mock_edit, mock_db):
        mock_edit.side_effect = core_exceptions.PermissionDeniedError(
            "Cannot edit health water intake for another user."
        )

        response = TestClient(_build_app(mock_db)).put(
            "/health_water", json={"id": 1, "user_id": 2, "amount_ml": 900}, headers=_HEADERS
        )

        assert response.status_code == 403


class TestDeleteHealthWater:
    @patch(f"{_SERVICE}.delete_health_water")
    def test_delete(self, mock_delete, mock_db):
        response = TestClient(_build_app(mock_db)).delete("/health_water/1", headers=_HEADERS)

        assert response.status_code == 204
        assert mock_delete.call_args.args[:2] == (1, 1)

    @patch(f"{_SERVICE}.delete_health_water")
    def test_not_found_is_404(self, mock_delete, mock_db):
        mock_delete.side_effect = core_exceptions.NotFoundError("Health water not found")

        response = TestClient(_build_app(mock_db)).delete("/health_water/9", headers=_HEADERS)

        assert response.status_code == 404
