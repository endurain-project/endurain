from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import core.dependencies as core_deps
    import modules.auth.dependencies as auth_deps
    import modules.health.health_fasting.router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/health_fasting")

    def _mock():
        return None

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = _uid
    app.dependency_overrides[core_deps.validate_pagination_values_on_query] = _mock
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadHealthFastingAllPagination:
    @patch("modules.health.health_fasting.router.health_fasting_crud.get_health_fasting_number_by_user_id")
    @patch("modules.health.health_fasting.router.health_fasting_crud.get_health_fasting_by_user_id")
    def test_list_success(self, mock_get, mock_get_number, mock_db):
        from modules.health.health_fasting.schema import HealthFastingRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [HealthFastingRead(id=1, user_id=1)]
        mock_get_number.return_value = 1

        response = client.get("/health_fasting", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    @patch("modules.health.health_fasting.router.health_fasting_crud.get_health_fasting_number_by_user_id")
    @patch("modules.health.health_fasting.router.health_fasting_crud.get_health_fasting_by_user_id")
    def test_list_empty(self, mock_get, mock_get_number, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = []
        mock_get_number.return_value = 0

        response = client.get("/health_fasting", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["records"] == []


class TestReadActiveFasting:
    @patch("modules.health.health_fasting.router.health_fasting_crud.get_active_fasting_by_user_id")
    def test_active_success(self, mock_get, mock_db):
        from modules.health.health_fasting.schema import HealthFastingRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = HealthFastingRead(id=1, user_id=1)

        response = client.get("/health_fasting/active", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200

    @patch("modules.health.health_fasting.router.health_fasting_crud.get_active_fasting_by_user_id")
    def test_active_none(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        response = client.get("/health_fasting/active", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() is None


class TestReadFastingStats:
    @patch("modules.health.health_fasting.router.health_fasting_crud.get_health_fasting_number_by_user_id")
    @patch("modules.health.health_fasting.router.health_fasting_crud.get_avg_fasting_duration")
    @patch("modules.health.health_fasting.router.health_fasting_crud.get_total_fasting_seconds")
    @patch("modules.health.health_fasting.router.health_fasting_crud.get_completed_fasting_count")
    @patch("modules.health.health_fasting.router.health_fasting_utils.calculate_streaks")
    def test_stats_success(
        self, mock_streaks, mock_completed_count, mock_total_seconds, mock_avg_dur, mock_started, mock_db
    ):
        client = TestClient(_build_app(mock_db))
        mock_completed_count.return_value = 10
        mock_total_seconds.return_value = 864000
        mock_avg_dur.return_value = 86400
        mock_streaks.return_value = (3, 10)
        mock_started.return_value = 12

        response = client.get("/health_fasting/stats", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        data = response.json()
        assert data["total_fasts"] == 10
        assert data["current_streak"] == 3
        assert data["longest_streak"] == 10
        assert data["completion_rate"] == 83.3

    @patch("modules.health.health_fasting.router.health_fasting_crud.get_health_fasting_number_by_user_id")
    @patch("modules.health.health_fasting.router.health_fasting_crud.get_avg_fasting_duration")
    @patch("modules.health.health_fasting.router.health_fasting_crud.get_total_fasting_seconds")
    @patch("modules.health.health_fasting.router.health_fasting_crud.get_completed_fasting_count")
    @patch("modules.health.health_fasting.router.health_fasting_utils.calculate_streaks")
    def test_stats_zero_started(
        self, mock_streaks, mock_completed_count, mock_total_seconds, mock_avg_dur, mock_started, mock_db
    ):
        client = TestClient(_build_app(mock_db))
        mock_completed_count.return_value = 0
        mock_total_seconds.return_value = 0
        mock_avg_dur.return_value = 0
        mock_streaks.return_value = (0, 0)
        mock_started.return_value = 0

        response = client.get("/health_fasting/stats", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json()["completion_rate"] == 0.0


class TestReadFastingById:
    @patch("modules.health.health_fasting.router.health_fasting_crud.get_health_fasting_by_id_and_user_id")
    def test_success(self, mock_get, mock_db):
        from modules.health.health_fasting.schema import HealthFastingRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = HealthFastingRead(id=1, user_id=1)

        response = client.get("/health_fasting/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200

    @patch("modules.health.health_fasting.router.health_fasting_crud.get_health_fasting_by_id_and_user_id")
    def test_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        response = client.get("/health_fasting/999", headers={"Authorization": "Bearer x"})
        assert response.status_code == 404


class TestCreateHealthFasting:
    @patch("modules.health.health_fasting.router.health_fasting_crud.create_health_fasting")
    @patch("modules.health.health_fasting.router.health_fasting_crud.get_active_fasting_by_user_id")
    def test_create_success(self, mock_active, mock_create, mock_db):
        from modules.health.health_fasting.schema import HealthFastingRead

        client = TestClient(_build_app(mock_db))
        mock_active.return_value = None
        mock_create.return_value = HealthFastingRead(id=1, user_id=1)

        response = client.post(
            "/health_fasting",
            json={"fast_start_time": "2024-01-15T08:00:00Z"},
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 201

    @patch("modules.health.health_fasting.router.health_fasting_crud.get_active_fasting_by_user_id")
    def test_create_already_active(self, mock_active, mock_db):
        from modules.health.health_fasting.schema import HealthFastingRead

        client = TestClient(_build_app(mock_db))
        mock_active.return_value = HealthFastingRead(id=1, user_id=1)

        response = client.post(
            "/health_fasting",
            json={"fast_start_time": "2024-01-15T08:00:00Z"},
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 400


class TestEditHealthFasting:
    @patch("modules.health.health_fasting.router.health_fasting_crud.edit_health_fasting")
    def test_edit_success(self, mock_edit, mock_db):
        from modules.health.health_fasting.schema import HealthFastingRead

        client = TestClient(_build_app(mock_db))
        mock_edit.return_value = HealthFastingRead(id=1, user_id=1)

        response = client.put(
            "/health_fasting",
            json={"id": 1, "user_id": 1},
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 200


class TestCompleteHealthFasting:
    @patch("modules.health.health_fasting.router.health_fasting_crud.complete_health_fasting")
    def test_complete_success(self, mock_complete, mock_db):
        from modules.health.health_fasting.schema import HealthFastingRead

        client = TestClient(_build_app(mock_db))
        mock_complete.return_value = HealthFastingRead(id=1, user_id=1)

        response = client.post(
            "/health_fasting/1/complete",
            json={"fast_end_time": "2024-01-15T10:00:00Z"},
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 200


class TestDeleteHealthFasting:
    @patch("modules.health.health_fasting.router.health_fasting_crud.delete_health_fasting")
    def test_delete_success(self, mock_delete, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.delete("/health_fasting/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 204
