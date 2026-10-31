from datetime import date
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import modules.auth.dependencies as auth_deps
    import modules.health.router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/health")

    def _mock():
        return None

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = _uid
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadHealthDailyStats:
    @patch("modules.health.router.health_weight_crud.get_latest_weight_by_user_id")
    @patch("modules.health.router.health_sleep_crud.get_health_sleep_by_date_and_user_id")
    @patch("modules.health.router.health_steps_crud.get_health_steps_by_date_and_user_id")
    @patch("modules.health.router.health_fasting_crud.get_active_fasting_by_user_id")
    @patch("modules.health.router.health_water_crud.get_health_water_by_date_and_user_id")
    @patch("modules.health.router.health_poop_crud.get_health_poop_by_date_and_user_id")
    @patch("modules.health.router.users_utils.user_local_today", return_value=date(2024, 1, 15))
    def test_all_data_present(
        self,
        _mock_today,
        mock_poop,
        mock_water,
        mock_fasting,
        mock_steps,
        mock_sleep,
        mock_weight,
        mock_db,
    ):
        client = TestClient(_build_app(mock_db))
        mock_sleep.return_value = MagicMock(
            total_sleep_seconds=28800,
            resting_heart_rate=50,
            hrv_status="balanced",
            avg_skin_temp_deviation=0.1,
        )
        mock_weight.return_value = MagicMock(weight=75.5, bmi=24.5)
        mock_steps.return_value = MagicMock(steps=8000)
        mock_fasting.return_value = MagicMock(
            id=1,
            fast_start_time="2024-01-15T08:00:00Z",
            fast_end_time=None,
            status="active",
            actual_duration_seconds=3600,
        )
        mock_water.return_value = MagicMock(amount_ml=1500.0)
        mock_poop.return_value = [MagicMock()]

        response = client.get("/health/stats/daily", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        data = response.json()
        assert data["sleep"] is not None
        assert data["weight"] is not None
        assert data["steps"] is not None
        assert data["fasting"] is not None
        assert data["water"] is not None
        assert data["poop"] is not None
        assert data["poop"]["count"] == 1

    @patch("modules.health.router.health_weight_crud.get_latest_weight_by_user_id")
    @patch("modules.health.router.health_sleep_crud.get_health_sleep_by_date_and_user_id")
    @patch("modules.health.router.health_steps_crud.get_health_steps_by_date_and_user_id")
    @patch("modules.health.router.health_fasting_crud.get_active_fasting_by_user_id")
    @patch("modules.health.router.health_water_crud.get_health_water_by_date_and_user_id")
    @patch("modules.health.router.health_poop_crud.get_health_poop_by_date_and_user_id")
    @patch("modules.health.router.users_utils.user_local_today", return_value=date(2024, 1, 15))
    def test_all_data_missing(
        self,
        _mock_today,
        mock_poop,
        mock_water,
        mock_fasting,
        mock_steps,
        mock_sleep,
        mock_weight,
        mock_db,
    ):
        client = TestClient(_build_app(mock_db))
        mock_sleep.return_value = None
        mock_weight.return_value = None
        mock_steps.return_value = None
        mock_fasting.return_value = None
        mock_water.return_value = None
        mock_poop.return_value = None

        response = client.get("/health/stats/daily", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        data = response.json()
        assert data["sleep"] is None
        assert data["weight"] is None
        assert data["steps"] is None
        assert data["fasting"] is None
        assert data["water"] is None
        assert data["poop"] is None
