from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_SERVICE = "modules.activities.activity_summaries.service"


@pytest.fixture(autouse=True)
def stub_user_local_today():
    """Pin the fallback anchor.

    Callers that omit ``date``/``year`` fall back to today in the *user's*
    timezone, which is a DB read the mocked session cannot serve.
    """
    with patch(
        f"{_SERVICE}.users_utils.user_local_today",
        return_value=date(2026, 3, 12),
    ) as mock:
        yield mock


def _build_app(mock_db):
    import core.database as core_db
    import core.exceptions as core_exceptions
    import modules.activities.activity_summaries.router as router
    import modules.auth.dependencies as auth_deps

    app = FastAPI()
    app.include_router(router.router, prefix="/activities/summaries")
    # Same domain-error boundary the real app registers, so these tests assert
    # the status codes clients actually receive.
    core_exceptions.register_exception_handlers(app)

    def _mock():
        return None

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = _uid
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadWeeklySummary:
    @patch(f"{_SERVICE}.summary_crud.get_weekly_summary")
    def test_weekly_summary_success(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        from modules.activities.activity_summaries.schema import WeeklySummaryResponse

        mock_get.return_value = WeeklySummaryResponse(breakdown=[], type_breakdown=None)

        response = client.get(
            "/activities/summaries?period=week&date=2024-01-15",
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 200
        # The route hands the parsed date straight through — no string parsing
        # of its own, unlike the previous ``/{view_type}`` handler.
        assert mock_get.call_args.kwargs["target_date"] == date(2024, 1, 15)

    def test_week_is_the_default_period(self, mock_db):
        from modules.activities.activity_summaries.schema import WeeklySummaryResponse

        with patch(f"{_SERVICE}.summary_crud.get_weekly_summary") as mock_get:
            mock_get.return_value = WeeklySummaryResponse(breakdown=[], type_breakdown=None)
            response = TestClient(_build_app(mock_db)).get(
                "/activities/summaries",
                headers={"Authorization": "Bearer x"},
            )
        assert response.status_code == 200
        mock_get.assert_called_once()

    def test_unknown_period_is_rejected(self, mock_db):
        response = TestClient(_build_app(mock_db)).get(
            "/activities/summaries?period=fortnight",
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 422

    def test_unparseable_date_is_rejected(self, mock_db):
        """FastAPI's ``date`` coercion replaced the hand-rolled parser."""
        response = TestClient(_build_app(mock_db)).get(
            "/activities/summaries?period=week&date=not-a-date",
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 422


class TestReadMonthlySummary:
    @patch(f"{_SERVICE}.summary_crud.get_monthly_summary")
    def test_monthly_summary_success(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        from modules.activities.activity_summaries.schema import MonthlySummaryResponse

        mock_get.return_value = MonthlySummaryResponse(breakdown=[], type_breakdown=None)

        response = client.get(
            "/activities/summaries?period=month&date=2024-01-15",
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 200
        # A month summary always starts on the 1st, whatever day the caller sent.
        assert mock_get.call_args.kwargs["target_date"] == date(2024, 1, 1)


class TestReadYearlySummary:
    @patch(f"{_SERVICE}.summary_crud.get_yearly_summary")
    def test_yearly_summary_success(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        from modules.activities.activity_summaries.schema import YearlySummaryResponse

        mock_get.return_value = YearlySummaryResponse(breakdown=[], type_breakdown=None)

        response = client.get(
            "/activities/summaries?period=year&year=2024",
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 200
        assert mock_get.call_args.kwargs["year"] == 2024

    @patch(f"{_SERVICE}.summary_crud.get_yearly_summary")
    def test_year_defaults_to_the_anchor_year(self, mock_get, mock_db):
        from modules.activities.activity_summaries.schema import YearlySummaryResponse

        mock_get.return_value = YearlySummaryResponse(breakdown=[], type_breakdown=None)

        response = TestClient(_build_app(mock_db)).get(
            "/activities/summaries?period=year",
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 200
        assert mock_get.call_args.kwargs["year"] == 2026


class TestReadLifetimeSummary:
    @patch(f"{_SERVICE}.summary_crud.get_lifetime_summary")
    def test_lifetime_summary_success(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        from modules.activities.activity_summaries.schema import LifetimeSummaryResponse

        mock_get.return_value = LifetimeSummaryResponse(breakdown=[], type_breakdown=None)

        response = client.get(
            "/activities/summaries?period=lifetime",
            headers={"Authorization": "Bearer x"},
        )
        assert response.status_code == 200


class TestYearValidation:
    """The year bound must not reject the caller's genuinely current year.

    The request carries no timezone, so validating against the server's UTC year
    rejected users east of UTC on 1 January (a UTC+13 user is already in the next
    year for 13 hours before the server is).
    """

    def test_accepts_a_year_ahead_of_the_server_utc_year(self):
        import modules.activities.activity_summaries.service as service

        assert service._latest_plausible_year() >= datetime.now(UTC).year

    def test_new_year_boundary_east_of_utc_is_accepted(self):
        import modules.activities.activity_summaries.service as service

        # 31 Dec 23:00 UTC -> already 1 Jan in UTC+13.
        with patch.object(service, "datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 12, 31, 23, 0, tzinfo=UTC)
            assert service._latest_plausible_year() == 2027

    def test_far_future_year_is_still_rejected(self, mock_db):
        resp = TestClient(_build_app(mock_db)).get(
            "/activities/summaries?period=year&year=3000",
            headers={"Authorization": "Bearer x"},
        )
        assert resp.status_code == 400
        assert "Invalid year" in resp.json()["detail"]
