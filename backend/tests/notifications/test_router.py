from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app(mock_db):
    import core.database as core_db
    import modules.auth.dependencies as auth_deps
    import modules.notifications.router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/notifications")

    def _mock():
        return None

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = _uid
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadNotificationsNumber:
    @patch("modules.notifications.router.notifications_service.count_notifications")
    def test_number_success(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = 5

        response = client.get("/notifications/number", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() == 5

    @patch("modules.notifications.router.notifications_service.count_notifications")
    def test_number_zero(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = 0

        response = client.get("/notifications/number", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() == 0


class TestReadNotificationById:
    @patch("modules.notifications.router.notifications_service.get_notification")
    def test_success(self, mock_get, mock_db):
        from modules.notifications.schema import NotificationRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = NotificationRead(id=1, user_id=1, read=False)

        response = client.get("/notifications/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json()["id"] == 1

    @patch("modules.notifications.router.notifications_service.get_notification")
    def test_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = None

        response = client.get("/notifications/999", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json() is None


class TestReadNotificationsPagination:
    @patch("modules.notifications.router.notifications_service.list_notifications")
    def test_pagination_success(self, mock_get, mock_db):
        from modules.notifications.schema import NotificationRead

        client = TestClient(_build_app(mock_db))
        mock_get.return_value = [NotificationRead(id=1, user_id=1, read=False)]

        response = client.get("/notifications/page_number/1/num_records/10", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200


class TestMarkNotificationAsRead:
    @patch("modules.notifications.router.notifications_service.mark_notification_as_read")
    def test_mark_read_success(self, mock_mark, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.put("/notifications/1/mark_as_read", headers={"Authorization": "Bearer x"})
        assert response.status_code == 204


class TestMarkAllNotificationsAsRead:
    @patch("modules.notifications.router.notifications_service.mark_all_notifications_as_read")
    def test_mark_all_read_success(self, mock_mark, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.put("/notifications/mark_all_as_read", headers={"Authorization": "Bearer x"})
        assert response.status_code == 204
        mock_mark.assert_called_once()


class TestPathValidation:
    def test_non_positive_notification_id_is_rejected(self, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.get("/notifications/0", headers={"Authorization": "Bearer x"})
        assert response.status_code == 422

    def test_non_positive_page_number_is_rejected(self, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.get("/notifications/page_number/0/num_records/10", headers={"Authorization": "Bearer x"})
        assert response.status_code == 422
