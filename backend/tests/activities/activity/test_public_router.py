from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import core.exceptions as core_exceptions
    import modules.activities.activity.public_router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/public/activities")
    # Same domain-error boundary the real app registers, so these tests assert
    # the status codes clients actually receive.
    core_exceptions.register_exception_handlers(app)
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


def _valid_activity(**kw):
    from modules.activities.activity.schema import Activity

    data = dict(
        distance=10000,
        name="Test",
        activity_type=1,
        start_time="2024-01-15T08:00:00Z",
        end_time="2024-01-15T09:00:00Z",
        timezone="UTC",
        total_elapsed_time=3600.0,
        total_timer_time=3600.0,
        calories=500,
        visibility=0,
        elevation_gain=50,
        elevation_loss=45,
        pace=300.0,
        average_hr=145,
        max_hr=175,
        average_speed=2.78,
        max_speed=5.0,
        city="City",
        town="Town",
        country="Country",
        description="desc",
        gear_id=1,
        id=1,
        user_id=1,
    )
    data.update(kw)
    return Activity(**data)


class TestReadPublicActivity:
    @patch(
        "modules.activities.activity.service.server_settings_integration.public_shareable_links_enabled",
        return_value=True,
    )
    @patch("modules.activities.activity.service.activities_crud.get_activity_by_id_if_is_public")
    def test_success(self, mock_get, _mock_settings, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = _valid_activity()

        response = client.get("/public/activities/1")
        assert response.status_code == 200
        assert response.json()["id"] == 1

    @patch(
        "modules.activities.activity.service.server_settings_integration.public_shareable_links_enabled",
        return_value=True,
    )
    @patch("modules.activities.activity.service.activities_crud.get_activity_by_id_if_is_public")
    def test_not_found(self, mock_get, _mock_settings, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        # Missing and not-public are the same answer on purpose: this endpoint is
        # unauthenticated, so distinguishing them would let anyone enumerate ids.
        response = client.get("/public/activities/999")
        assert response.status_code == 404
        assert response.json()["detail"] == "Activity not found"

    @patch(
        "modules.activities.activity.service.server_settings_integration.public_shareable_links_enabled",
        return_value=False,
    )
    @patch("modules.activities.activity.service.activities_crud.get_activity_by_id_if_is_public")
    def test_disabled_shareable_links_never_touch_persistence(self, mock_get, _mock_settings, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.get("/public/activities/1")
        assert response.status_code == 404
        mock_get.assert_not_called()
