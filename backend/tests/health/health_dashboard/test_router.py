import uuid
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.health.health_dashboard.schema as health_dashboard_schema
import modules.health.health_targets.schema as health_targets_schema

_ID = uuid.uuid4()


_USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


def _build_app(mock_db, scopes=frozenset({"health:read", "health-targets:read"})):
    import core.database as core_db
    import modules.auth.dependencies as auth_deps
    import modules.health.health_dashboard.router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/health")

    def _mock():
        return None

    def _uid():
        return _USER_ID

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[auth_deps.get_current_user_id] = _uid
    app.dependency_overrides[auth_deps.get_current_scopes] = lambda: scopes
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadHealthDailyStats:
    @patch("modules.health.health_dashboard.router.health_dashboard_service.get_daily_stats")
    def test_returns_the_dashboard(self, mock_stats, mock_db):
        mock_stats.return_value = health_dashboard_schema.HealthDashboardResponse(
            steps=health_dashboard_schema.HealthStepsDashboard(steps=8000),
            poop=health_dashboard_schema.HealthPoopDashboard(count=1),
            targets=health_targets_schema.HealthTargetsRead(
                updated_at="2024-01-01T00:00:00Z",
                id=_ID,
                user_id=_USER_ID,
                version=3,
                sleep_seconds=28800,
                steps=8000,
                weight_kg=70.0,
                fasting_seconds=57600,
                water_ml=2000,
                poop_count=1,
            ),
        )

        response = TestClient(_build_app(mock_db)).get("/health/stats/daily", headers={"Authorization": "Bearer x"})

        assert response.status_code == 200
        data = response.json()
        assert data["steps"] == {"steps": 8000}
        assert data["poop"] == {"count": 1}
        assert data["targets"]["steps"] == 8000
        assert data["sleep"] is None
        assert mock_stats.call_args.args[0] == _USER_ID
        assert mock_stats.call_args.kwargs == {"include_targets": True}

    @patch("modules.health.health_dashboard.router.health_dashboard_service.get_daily_stats")
    def test_targets_are_withheld_without_the_targets_scope(self, mock_stats, mock_db):
        mock_stats.return_value = health_dashboard_schema.HealthDashboardResponse(targets=None)

        response = TestClient(_build_app(mock_db, frozenset({"health:read"}))).get(
            "/health/stats/daily", headers={"Authorization": "Bearer x"}
        )

        assert response.status_code == 200
        assert response.json()["targets"] is None
        assert mock_stats.call_args.kwargs == {"include_targets": False}
