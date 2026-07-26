from datetime import UTC, datetime
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import modules.activities.activity_summaries.router as router
    import modules.auth.dependencies as auth_deps

    app = FastAPI()
    app.include_router(router.router, prefix="/activities_summaries")

    def _mock():
        return None

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = _uid
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadWeeklySummary:
    @patch("modules.activities.activity_summaries.router.summary_crud.get_weekly_summary")
    def test_weekly_summary_success(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        from modules.activities.activity_summaries.schema import WeeklySummaryResponse

        mock_get.return_value = WeeklySummaryResponse(breakdown=[], type_breakdown=None)

        response = client.get(
            "/activities_summaries/week?target_date_str=2024-01-15",
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 200


class TestReadMonthlySummary:
    @patch("modules.activities.activity_summaries.router.summary_crud.get_monthly_summary")
    def test_monthly_summary_success(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        from modules.activities.activity_summaries.schema import MonthlySummaryResponse

        mock_get.return_value = MonthlySummaryResponse(breakdown=[], type_breakdown=None)

        response = client.get(
            "/activities_summaries/month?target_date_str=2024-01-15",
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 200


class TestReadYearlySummary:
    @patch("modules.activities.activity_summaries.router.summary_crud.get_yearly_summary")
    def test_yearly_summary_success(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        from modules.activities.activity_summaries.schema import YearlySummaryResponse

        mock_get.return_value = YearlySummaryResponse(breakdown=[], type_breakdown=None)

        response = client.get(
            "/activities_summaries/year?year=2024",
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 200


class TestReadLifetimeSummary:
    @patch("modules.activities.activity_summaries.router.summary_crud.get_lifetime_summary")
    def test_lifetime_summary_success(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        from modules.activities.activity_summaries.schema import LifetimeSummaryResponse

        mock_get.return_value = LifetimeSummaryResponse(breakdown=[], type_breakdown=None)

        response = client.get("/activities_summaries/lifetime", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200


class TestYearValidation:
    """The year bound must not reject the caller's genuinely current year.

    The request carries no timezone, so validating against the server's UTC year
    rejected users east of UTC on 1 January (a UTC+13 user is already in the next
    year for 13 hours before the server is).
    """

    def test_accepts_a_year_ahead_of_the_server_utc_year(self):
        from datetime import UTC, datetime

        import modules.activities.activity_summaries.router as router

        assert router._latest_plausible_year() >= datetime.now(UTC).year

    def test_new_year_boundary_east_of_utc_is_accepted(self):
        import modules.activities.activity_summaries.router as router

        # 31 Dec 23:00 UTC -> already 1 Jan in UTC+13.
        with patch.object(router, "datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 12, 31, 23, 0, tzinfo=UTC)
            assert router._latest_plausible_year() == 2027

    def test_far_future_year_is_still_rejected(self, mock_db):
        resp = TestClient(_build_app(mock_db)).get(
            "/activities_summaries/year?year=3000",
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 400
        assert "Invalid year" in resp.json()["detail"]
