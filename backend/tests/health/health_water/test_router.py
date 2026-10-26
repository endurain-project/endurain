from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions
import core.pagination as core_pagination
from modules.health.health_water.schema import HealthWaterRead

_SERVICE = "modules.health.health_water.router.health_water_service"
_HEADERS = {"Authorization": "Bearer x"}


def _build_app(mock_db):
    import core.database as core_db
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
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadHealthWaterAllPagination:
    @patch(f"{_SERVICE}.list_health_water")
    def test_list_success(self, mock_list, mock_db):
        mock_list.return_value = core_pagination.Page(
            items=[HealthWaterRead(id=1, user_id=1)], total=1, page=1, num_records=25
        )

        response = TestClient(_build_app(mock_db)).get("/health_water", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json()["total"] == 1

    @patch(f"{_SERVICE}.list_health_water")
    def test_list_empty(self, mock_list, mock_db):
        mock_list.return_value = core_pagination.Page(items=[], total=0, page=1, num_records=25)

        response = TestClient(_build_app(mock_db)).get("/health_water", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json()["items"] == []

    @patch(f"{_SERVICE}.list_health_water")
    def test_passes_pagination_and_interval_through(self, mock_list, mock_db):
        mock_list.return_value = core_pagination.Page(items=[], total=0, page=1, num_records=25)

        TestClient(_build_app(mock_db)).get(
            "/health_water?page_number=2&num_records=10&interval=last_30_days", headers=_HEADERS
        )

        args = mock_list.call_args
        assert args.args[0] == 1
        assert (args.kwargs["page_number"], args.kwargs["num_records"]) == (2, 10)
        assert args.kwargs["interval"].value == "last_30_days"


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

        response = TestClient(_build_app(mock_db)).patch(
            "/health_water/1", json={"amount_ml": 900}, headers={**_HEADERS, "If-Match": '"1"'}
        )

        assert response.status_code == 200
        assert response.json()["amount_ml"] == 900.0

    @patch(f"{_SERVICE}.edit_health_water")
    def test_not_found_is_404(self, mock_edit, mock_db):
        mock_edit.side_effect = core_exceptions.NotFoundError("Health water not found")

        response = TestClient(_build_app(mock_db)).patch(
            "/health_water/9", json={"amount_ml": 900}, headers={**_HEADERS, "If-Match": '"1"'}
        )

        assert response.status_code == 404


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
