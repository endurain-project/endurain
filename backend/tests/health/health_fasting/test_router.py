from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions
import core.pagination as core_pagination
from modules.health.health_fasting.schema import (
    HealthFastingRead,
    HealthFastingStatsResponse,
)

_SERVICE = "modules.health.health_fasting.router.health_fasting_service"
_HEADERS = {"Authorization": "Bearer x"}
_IF_MATCH_HEADERS = {**_HEADERS, "If-Match": '"1"'}
_START = {"fast_start_time": "2024-01-15T08:00:00Z"}


def _build_app(mock_db):
    import core.database as core_db
    import modules.auth.dependencies as auth_deps
    import modules.health.health_fasting.router as router

    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(router.router, prefix="/health_fasting")

    def _mock():
        return None

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = _uid
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


def _client(mock_db) -> TestClient:
    return TestClient(_build_app(mock_db))


class TestReadHealthFastingAllPagination:
    @patch(f"{_SERVICE}.list_health_fasting")
    def test_list_success(self, mock_list, mock_db):
        mock_list.return_value = core_pagination.Page(
            items=[HealthFastingRead(id=1, user_id=1)], total=1, page=1, num_records=25
        )

        response = _client(mock_db).get("/health_fasting", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json()["total"] == 1

    @patch(f"{_SERVICE}.list_health_fasting")
    def test_passes_pagination_and_interval_through(self, mock_list, mock_db):
        mock_list.return_value = core_pagination.Page(items=[], total=0, page=1, num_records=25)

        _client(mock_db).get("/health_fasting?page_number=2&num_records=10&interval=last_30_days", headers=_HEADERS)

        args = mock_list.call_args
        assert args.args[0] == 1
        assert (args.kwargs["page_number"], args.kwargs["num_records"]) == (2, 10)
        assert args.kwargs["interval"].value == "last_30_days"


class TestReadActiveFasting:
    @patch(f"{_SERVICE}.get_active_fasting")
    def test_active(self, mock_active, mock_db):
        mock_active.return_value = HealthFastingRead(id=1, user_id=1)

        response = _client(mock_db).get("/health_fasting/active", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json()["id"] == 1

    @patch(f"{_SERVICE}.get_active_fasting", return_value=None)
    def test_none(self, _active, mock_db):
        response = _client(mock_db).get("/health_fasting/active", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json() is None


class TestReadFastingStats:
    @patch(f"{_SERVICE}.get_fasting_stats")
    def test_stats(self, mock_stats, mock_db):
        mock_stats.return_value = HealthFastingStatsResponse(
            total_fasts=3,
            current_streak=2,
            longest_streak=3,
            avg_duration_seconds=50000,
            total_fasting_seconds=150000,
            completion_rate=75.0,
        )

        response = _client(mock_db).get("/health_fasting/stats", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json()["completion_rate"] == 75.0


class TestReadFastingById:
    @patch(f"{_SERVICE}.get_health_fasting")
    def test_success(self, mock_get, mock_db):
        mock_get.return_value = HealthFastingRead(id=1, user_id=1)

        response = _client(mock_db).get("/health_fasting/1", headers=_HEADERS)

        assert response.status_code == 200
        assert mock_get.call_args.args[:2] == (1, 1)

    @patch(f"{_SERVICE}.get_health_fasting")
    def test_not_found(self, mock_get, mock_db):
        mock_get.side_effect = core_exceptions.NotFoundError("Fasting record not found")

        assert _client(mock_db).get("/health_fasting/999", headers=_HEADERS).status_code == 404


class TestCreateHealthFasting:
    @patch(f"{_SERVICE}.create_health_fasting")
    def test_create_success(self, mock_create, mock_db):
        mock_create.return_value = HealthFastingRead(id=1, user_id=1)

        assert _client(mock_db).post("/health_fasting", json=_START, headers=_HEADERS).status_code == 201

    @patch(f"{_SERVICE}.create_health_fasting")
    def test_already_active_is_400(self, mock_create, mock_db):
        mock_create.side_effect = core_exceptions.InvalidInputError("User already has an active fasting session.")

        assert _client(mock_db).post("/health_fasting", json=_START, headers=_HEADERS).status_code == 400


class TestEditHealthFasting:
    @patch(f"{_SERVICE}.edit_health_fasting")
    def test_edit_success(self, mock_edit, mock_db):
        mock_edit.return_value = HealthFastingRead(id=1, user_id=1)

        response = _client(mock_db).patch("/health_fasting/1", json={}, headers={**_HEADERS, "If-Match": '"1"'})

        assert response.status_code == 200


class TestCompleteHealthFasting:
    @patch(f"{_SERVICE}.complete_health_fasting")
    def test_complete_success(self, mock_complete, mock_db):
        mock_complete.return_value = HealthFastingRead(id=1, user_id=1)

        response = _client(mock_db).post(
            "/health_fasting/1/complete",
            json={"fast_end_time": "2024-01-16T08:00:00Z", "status": "completed"},
            headers={**_HEADERS, "If-Match": '"3"'},
        )

        assert response.status_code == 200
        assert mock_complete.call_args.args[:2] == (1, 1)
        assert mock_complete.call_args.kwargs["if_match"] == '"3"'
        assert response.headers["ETag"]

    @patch(f"{_SERVICE}.complete_health_fasting")
    def test_not_in_progress_is_400(self, mock_complete, mock_db):
        mock_complete.side_effect = core_exceptions.InvalidInputError("Fasting session is not in progress")

        response = _client(mock_db).post(
            "/health_fasting/1/complete",
            json={"fast_end_time": "2024-01-16T08:00:00Z", "status": "completed"},
            headers={**_HEADERS, "If-Match": '"3"'},
        )

        assert response.status_code == 400


class TestDeleteHealthFasting:
    @patch(f"{_SERVICE}.delete_health_fasting")
    def test_delete_success(self, mock_delete, mock_db):
        response = _client(mock_db).delete("/health_fasting/1", headers=_IF_MATCH_HEADERS)

        assert response.status_code == 204
        assert mock_delete.call_args.args[:2] == (1, 1)
        assert mock_delete.call_args.kwargs == {"if_match": '"1"'}

    @patch(f"{_SERVICE}.delete_health_fasting")
    def test_not_found_is_404(self, mock_delete, mock_db):
        mock_delete.side_effect = core_exceptions.NotFoundError("Health fasting not found")

        assert _client(mock_db).delete("/health_fasting/9", headers=_IF_MATCH_HEADERS).status_code == 404


class TestReadSendsTheETag:
    @patch(f"{_SERVICE}.get_health_fasting")
    def test_a_record_read_by_id_carries_its_version(self, mock_get, mock_db):
        mock_get.return_value = HealthFastingRead(id=1, user_id=1, version=5)

        response = _client(mock_db).get("/health_fasting/1", headers=_HEADERS)

        assert response.headers["ETag"] == '"5"'

    @patch(f"{_SERVICE}.get_active_fasting")
    def test_the_active_fast_carries_its_version(self, mock_active, mock_db):
        mock_active.return_value = HealthFastingRead(id=1, user_id=1, version=3)

        response = _client(mock_db).get("/health_fasting/active", headers=_HEADERS)

        assert response.headers["ETag"] == '"3"'

    @patch(f"{_SERVICE}.get_active_fasting", return_value=None)
    def test_no_active_fast_has_no_tag(self, _active, mock_db):
        response = _client(mock_db).get("/health_fasting/active", headers=_HEADERS)

        assert "ETag" not in response.headers
