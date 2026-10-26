"""The combined activity detail routes."""

from datetime import UTC, datetime
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions
from modules.activities.activity.schema import ActivityRead
from modules.activities.activity_detail.schema import ActivityDetailRead
from modules.activities.activity_laps.schema import ActivityLapsPage
from modules.activities.activity_sets.schema import ActivitySetsPage
from modules.activities.activity_workout_steps.schema import ActivityWorkoutStepsPage


def _build_app(mock_db):
    import core.database as core_db
    import modules.activities.activity_detail.public_router as public_router
    import modules.activities.activity_detail.router as router
    import modules.auth.dependencies as auth_deps

    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(router.router, prefix="/activities/{activity_id}")
    app.include_router(public_router.router, prefix="/public/activities/{activity_id}")
    app.dependency_overrides[auth_deps.check_scopes] = lambda: None
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: 1
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


def _detail() -> ActivityDetailRead:
    activity = ActivityRead(
        id=5,
        user_id=1,
        name="Run",
        activity_type=1,
        start_time=datetime(2024, 1, 15, 8, tzinfo=UTC),
        end_time=datetime(2024, 1, 15, 9, tzinfo=UTC),
        total_elapsed_time=3600,
        total_timer_time=3500,
        distance=10000,
        visibility=0,
        version=4,
    )
    return ActivityDetailRead(
        activity=activity,
        laps=ActivityLapsPage.build([], 0, 1, 200),
        sets=ActivitySetsPage.build([], 0, 1, 200),
        workout_steps=ActivityWorkoutStepsPage.build([], 0, 1, 200),
    )


class TestAuthenticatedDetail:
    @patch("modules.activities.activity_detail.router.activity_detail_service.get_activity_detail")
    def test_returns_the_activity_and_its_collections(self, mock_get, mock_db):
        mock_get.return_value = _detail()

        response = TestClient(_build_app(mock_db)).get("/activities/5/detail", headers={"Authorization": "Bearer x"})

        assert response.status_code == 200
        body = response.json()
        assert body["activity"]["id"] == 5
        assert set(body) == {"activity", "laps", "sets", "workout_steps"}
        assert body["laps"]["total"] == 0
        mock_get.assert_called_once_with(5, 1, mock_db)

    @patch("modules.activities.activity_detail.router.activity_detail_service.get_activity_detail")
    def test_carries_the_activitys_etag_for_a_later_save(self, mock_get, mock_db):
        mock_get.return_value = _detail()

        response = TestClient(_build_app(mock_db)).get("/activities/5/detail", headers={"Authorization": "Bearer x"})

        assert response.headers["ETag"] == '"4"'

    @patch("modules.activities.activity_detail.router.activity_detail_service.get_activity_detail")
    def test_an_invisible_activity_is_not_found(self, mock_get, mock_db):
        mock_get.side_effect = core_exceptions.NotFoundError("nope")

        response = TestClient(_build_app(mock_db)).get("/activities/5/detail", headers={"Authorization": "Bearer x"})

        assert response.status_code == 404

    def test_a_non_positive_activity_id_is_rejected(self, mock_db):
        response = TestClient(_build_app(mock_db)).get("/activities/0/detail", headers={"Authorization": "Bearer x"})

        assert response.status_code == 422


class TestPublicDetail:
    @patch("modules.activities.activity_detail.public_router.activity_detail_service.get_public_activity_detail")
    def test_returns_the_activity_and_its_collections_without_credentials(self, mock_get, mock_db):
        mock_get.return_value = _detail()

        response = TestClient(_build_app(mock_db)).get("/public/activities/5/detail")

        assert response.status_code == 200
        assert response.json()["activity"]["id"] == 5
        mock_get.assert_called_once_with(5, mock_db)

    @patch("modules.activities.activity_detail.public_router.activity_detail_service.get_public_activity_detail")
    def test_an_activity_that_is_not_public_is_not_found(self, mock_get, mock_db):
        mock_get.side_effect = core_exceptions.NotFoundError("nope")

        response = TestClient(_build_app(mock_db)).get("/public/activities/5/detail")

        assert response.status_code == 404
