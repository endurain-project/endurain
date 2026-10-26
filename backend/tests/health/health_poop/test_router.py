from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions
import core.pagination as core_pagination
from modules.health.health_poop.schema import HealthPoopRead

_SERVICE = "modules.health.health_poop.router.health_poop_service"
_HEADERS = {"Authorization": "Bearer x"}


def _build_app(mock_db):
    import core.database as core_db
    import modules.auth.dependencies as auth_deps
    import modules.health.health_poop.router as router

    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(router.router, prefix="/health_poop")

    def _mock():
        return None

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = _uid
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadHealthPoopAllPagination:
    @patch(f"{_SERVICE}.list_health_poop")
    def test_list_success(self, mock_list, mock_db):
        mock_list.return_value = core_pagination.Page(
            items=[HealthPoopRead(id=1, user_id=1)], total=1, page=1, num_records=25
        )

        response = TestClient(_build_app(mock_db)).get("/health_poop", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json()["total"] == 1

    @patch(f"{_SERVICE}.list_health_poop")
    def test_list_empty(self, mock_list, mock_db):
        mock_list.return_value = core_pagination.Page(items=[], total=0, page=1, num_records=25)

        response = TestClient(_build_app(mock_db)).get("/health_poop", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json()["items"] == []

    @patch(f"{_SERVICE}.list_health_poop")
    def test_passes_pagination_and_interval_through(self, mock_list, mock_db):
        mock_list.return_value = core_pagination.Page(items=[], total=0, page=1, num_records=25)

        TestClient(_build_app(mock_db)).get(
            "/health_poop?page_number=2&num_records=10&interval=last_30_days", headers=_HEADERS
        )

        args = mock_list.call_args
        assert args.args[0] == 1
        assert (args.kwargs["page_number"], args.kwargs["num_records"]) == (2, 10)
        assert args.kwargs["interval"].value == "last_30_days"


class TestReadHealthPoopById:
    @patch(f"{_SERVICE}.get_health_poop")
    def test_success(self, mock_get, mock_db):
        mock_get.return_value = HealthPoopRead(id=1, user_id=1)

        response = TestClient(_build_app(mock_db)).get("/health_poop/1", headers=_HEADERS)

        assert response.status_code == 200
        assert mock_get.call_args.args[:2] == (1, 1)

    @patch(f"{_SERVICE}.get_health_poop")
    def test_not_found(self, mock_get, mock_db):
        mock_get.side_effect = core_exceptions.NotFoundError("Poop record not found")

        response = TestClient(_build_app(mock_db)).get("/health_poop/999", headers=_HEADERS)

        assert response.status_code == 404


class TestCreateHealthPoop:
    @patch(f"{_SERVICE}.create_health_poop")
    def test_create_success(self, mock_create, mock_db):
        mock_create.return_value = HealthPoopRead(id=1, user_id=1)

        response = TestClient(_build_app(mock_db)).post(
            "/health_poop", json={"date_time": "2024-01-15T10:00:00"}, headers=_HEADERS
        )

        assert response.status_code == 201


class TestEditHealthPoop:
    @patch(f"{_SERVICE}.edit_health_poop")
    def test_edit_success(self, mock_edit, mock_db):
        mock_edit.return_value = HealthPoopRead(id=1, user_id=1)

        response = TestClient(_build_app(mock_db)).patch(
            "/health_poop/1", json={}, headers={**_HEADERS, "If-Match": '"1"'}
        )

        assert response.status_code == 200


class TestDeleteHealthPoop:
    @patch(f"{_SERVICE}.delete_health_poop")
    def test_delete_success(self, mock_delete, mock_db):
        response = TestClient(_build_app(mock_db)).delete("/health_poop/1", headers=_HEADERS)

        assert response.status_code == 204
        assert mock_delete.call_args.args[:2] == (1, 1)


class TestReadSendsTheETag:
    @patch(f"{_SERVICE}.get_health_poop")
    def test_a_record_read_by_id_carries_its_version(self, mock_get, mock_db):
        mock_get.return_value = HealthPoopRead(id=1, user_id=1, version=5)

        response = TestClient(_build_app(mock_db)).get("/health_poop/1", headers=_HEADERS)

        assert response.headers["ETag"] == '"5"'
