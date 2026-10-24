from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import modules.health.health_dashboard.schema as health_dashboard_schema


def _build_app(mock_db):
    import core.database as core_db
    import modules.auth.dependencies as auth_deps
    import modules.health.health_dashboard.router as router

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
    @patch("modules.health.health_dashboard.router.health_dashboard_service.get_daily_stats")
    def test_returns_the_dashboard(self, mock_stats, mock_db):
        mock_stats.return_value = health_dashboard_schema.HealthDashboardResponse(
            steps=health_dashboard_schema.HealthStepsDashboard(steps=8000),
            poop=health_dashboard_schema.HealthPoopDashboard(count=1),
        )

        response = TestClient(_build_app(mock_db)).get("/health/stats/daily", headers={"Authorization": "Bearer x"})

        assert response.status_code == 200
        data = response.json()
        assert data["steps"] == {"steps": 8000}
        assert data["poop"] == {"count": 1}
        assert data["sleep"] is None
        assert mock_stats.call_args.args[0] == 1
