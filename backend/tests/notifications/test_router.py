from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.notifications.schema as notifications_schema


def _read(**fields):
    """Build a stored new-activity notification."""
    import modules.notifications.schema as notifications_schema

    return notifications_schema.NOTIFICATION_READ_ADAPTER.validate_python(
        {
            "id": 1,
            "user_id": 1,
            "type": "new_activity",
            "options": {"activity_id": 5},
            "created_at": datetime(2024, 1, 1),
            **fields,
        }
    )


def _build_app(mock_db):
    import core.database as core_db
    import modules.auth.dependencies as auth_deps
    import modules.notifications.router as router

    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(router.router, prefix="/notifications")

    def _mock():
        return None

    def _uid():
        return 1

    app.dependency_overrides[auth_deps.check_scopes] = _mock
    app.dependency_overrides[auth_deps.get_current_user_id] = _uid
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestReadUnreadCount:
    @patch("modules.notifications.router.notifications_service.count_unread_notifications")
    def test_unread_count(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = 5

        response = client.get("/notifications/unread-count", headers={"Authorization": "Bearer x"})

        assert response.status_code == 200
        assert response.json() == {"count": 5}
        mock_get.assert_called_once_with(1, mock_db)

    def test_the_old_number_route_is_gone(self, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.get("/notifications/number", headers={"Authorization": "Bearer x"})

        assert response.status_code == 422


class TestReadNotificationById:
    @patch("modules.notifications.router.notifications_service.get_notification")
    def test_success(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = _read(read=False)

        response = client.get("/notifications/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json()["id"] == 1

    @patch("modules.notifications.router.notifications_service.get_notification")
    def test_created_at_is_full_utc_iso_timestamp(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = _read(read=False, created_at=datetime(2026, 7, 16, 10, 30))

        response = client.get("/notifications/1", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json()["created_at"] == "2026-07-16T10:30:00Z"

    @patch("modules.notifications.router.notifications_service.get_notification")
    def test_not_found(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.side_effect = core_exceptions.NotFoundError("Notification not found")

        response = client.get("/notifications/999", headers={"Authorization": "Bearer x"})
        assert response.status_code == 404


class TestReadNotificationsPagination:
    @patch("modules.notifications.router.notifications_service.list_notifications")
    def test_first_slice_success(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = notifications_schema.NotificationPage(
            items=[_read(read=False)], num_records=10, next_cursor="abc"
        )

        response = client.get("/notifications?num_records=10", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        body = response.json()
        assert body["next_cursor"] == "abc"
        assert "total" not in body
        assert body["items"][0]["id"] == 1
        mock_get.assert_called_once_with(1, mock_db, cursor=None, num_records=10, unread_only=False)

    @patch("modules.notifications.router.notifications_service.list_notifications")
    def test_cursor_and_default_size_are_forwarded(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = notifications_schema.NotificationPage(items=[], num_records=25)

        response = client.get("/notifications?cursor=abc", headers={"Authorization": "Bearer x"})

        assert response.status_code == 200
        mock_get.assert_called_once_with(
            1, mock_db, cursor="abc", num_records=core_pagination.DEFAULT_NUM_RECORDS, unread_only=False
        )

    @patch("modules.notifications.router.notifications_service.list_notifications")
    def test_unread_only_is_forwarded_to_the_service(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = notifications_schema.NotificationPage(items=[], num_records=1)

        response = client.get("/notifications?unread_only=true&num_records=1", headers={"Authorization": "Bearer x"})

        assert response.status_code == 200
        mock_get.assert_called_once_with(1, mock_db, cursor=None, num_records=1, unread_only=True)

    @patch("modules.notifications.router.notifications_service.list_notifications")
    def test_created_at_is_full_utc_iso_timestamp(self, mock_get, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_get.return_value = notifications_schema.NotificationPage(
            items=[_read(read=False, created_at=datetime(2026, 7, 16, 10, 30))], num_records=10
        )

        response = client.get("/notifications?num_records=10", headers={"Authorization": "Bearer x"})
        assert response.status_code == 200
        assert response.json()["items"][0]["created_at"] == "2026-07-16T10:30:00Z"

    def test_a_bad_cursor_is_a_400(self, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        response = client.get("/notifications?cursor=garbage", headers={"Authorization": "Bearer x"})

        assert response.status_code == 400


class TestMarkNotificationAsRead:
    @patch("modules.notifications.router.notifications_service.mark_notification_as_read")
    def test_mark_read_success(self, mock_mark, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.post("/notifications/1/read", headers={"Authorization": "Bearer x"})
        assert response.status_code == 204

    @patch("modules.notifications.router.notifications_service.mark_notification_as_read")
    def test_mark_read_missing_is_404(self, mock_mark, mock_db):
        client = TestClient(_build_app(mock_db))
        mock_mark.side_effect = core_exceptions.NotFoundError("Notification not found")

        response = client.post("/notifications/9/read", headers={"Authorization": "Bearer x"})
        assert response.status_code == 404


class TestMarkAllNotificationsAsRead:
    @patch("modules.notifications.router.notifications_service.mark_all_notifications_as_read")
    def test_mark_all_read_success(self, mock_mark, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.post("/notifications/read", headers={"Authorization": "Bearer x"})
        assert response.status_code == 204
        mock_mark.assert_called_once()


class TestPathValidation:
    def test_non_positive_notification_id_is_rejected(self, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.get("/notifications/0", headers={"Authorization": "Bearer x"})
        assert response.status_code == 422

    def test_oversized_page_is_rejected(self, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.get(
            f"/notifications?num_records={core_pagination.MAX_NUM_RECORDS + 1}", headers={"Authorization": "Bearer x"}
        )
        assert response.status_code == 422

    def test_non_positive_size_is_rejected(self, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.get("/notifications?num_records=0", headers={"Authorization": "Bearer x"})
        assert response.status_code == 422


class TestMarkNotificationsAsRead:
    @patch("modules.notifications.router.notifications_service.mark_notifications_as_read")
    def test_ids_mark_only_those(self, mock_mark, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.post("/notifications/read", json={"ids": [3, 4]}, headers={"Authorization": "Bearer x"})

        assert response.status_code == 204
        mock_mark.assert_called_once_with([3, 4], 1, mock_db)

    @patch("modules.notifications.router.notifications_service.mark_all_notifications_as_read")
    def test_no_body_still_marks_everything(self, mock_all, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.post("/notifications/read", headers={"Authorization": "Bearer x"})

        assert response.status_code == 204
        mock_all.assert_called_once_with(1, mock_db)

    @pytest.mark.parametrize(
        "body",
        [{"ids": []}, {"ids": list(range(1, 102))}, {"ids": [0]}, {"ids": ["a"]}, {"ids": [1], "all": True}, {}],
    )
    @patch("modules.notifications.router.notifications_service.mark_notifications_as_read")
    def test_a_bad_list_is_refused(self, mock_mark, body, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.post("/notifications/read", json=body, headers={"Authorization": "Bearer x"})

        assert response.status_code == 422
        mock_mark.assert_not_called()


class TestDeleteNotification:
    @patch("modules.notifications.router.notifications_service.delete_notification")
    def test_delete_answers_204(self, mock_delete, mock_db):
        client = TestClient(_build_app(mock_db))

        response = client.delete("/notifications/7", headers={"Authorization": "Bearer x"})

        assert response.status_code == 204
        mock_delete.assert_called_once_with(7, 1, mock_db)

    @patch("modules.notifications.router.notifications_service.delete_notification")
    def test_someone_elses_or_a_missing_id_is_404(self, mock_delete, mock_db):
        mock_delete.side_effect = core_exceptions.NotFoundError("Notification not found")
        client = TestClient(_build_app(mock_db))

        response = client.delete("/notifications/7", headers={"Authorization": "Bearer x"})

        assert response.status_code == 404
