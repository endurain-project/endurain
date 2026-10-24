from datetime import date as datetime_date
from unittest.mock import patch

import core.exceptions as core_exceptions
import modules.health.health_sleep.schema as health_sleep_schema

_SERVICE = "modules.health.health_sleep.router.health_sleep_service"
_HEADERS = {"Authorization": "Bearer mock_token"}


def _record(record_id: int = 1, day: int = 15, seconds: int = 28800) -> health_sleep_schema.HealthSleepRead:
    return health_sleep_schema.HealthSleepRead(
        id=record_id, user_id=1, date=datetime_date(2024, 1, day), total_sleep_seconds=seconds
    )


class TestReadHealthSleepAll:
    @patch(f"{_SERVICE}.list_health_sleep")
    def test_returns_the_page_and_total(self, mock_list, fast_api_client, fast_api_app):
        mock_list.return_value = health_sleep_schema.HealthSleepListResponse(
            total=2, records=[_record(1, 15, 28800), _record(2, 16, 30000)]
        )

        response = fast_api_client.get("/health_sleep", headers=_HEADERS)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert [r["total_sleep_seconds"] for r in data["records"]] == [28800, 30000]

    @patch(f"{_SERVICE}.list_health_sleep")
    def test_empty(self, mock_list, fast_api_client, fast_api_app):
        mock_list.return_value = health_sleep_schema.HealthSleepListResponse(total=0, records=[])

        response = fast_api_client.get("/health_sleep", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json()["records"] == []

    @patch(f"{_SERVICE}.list_health_sleep")
    def test_passes_pagination_and_interval_through(self, mock_list, fast_api_client, fast_api_app):
        mock_list.return_value = health_sleep_schema.HealthSleepListResponse(
            total=0, num_records=10, page_number=2, records=[]
        )

        response = fast_api_client.get(
            "/health_sleep?page_number=2&num_records=10&interval=last_30_days", headers=_HEADERS
        )

        assert response.status_code == 200
        args = mock_list.call_args.args
        assert args[0] == 1
        assert args[2:4] == (2, 10)
        assert args[4].value == "last_30_days"


class TestCreateHealthSleep:
    @patch(f"{_SERVICE}.create_health_sleep")
    def test_creates(self, mock_create, fast_api_client, fast_api_app):
        mock_create.return_value = _record()

        response = fast_api_client.post(
            "/health_sleep", json={"date": "2024-01-15", "total_sleep_seconds": 28800}, headers=_HEADERS
        )

        assert response.status_code == 201
        assert response.json()["total_sleep_seconds"] == 28800

    @patch(f"{_SERVICE}.create_health_sleep")
    def test_missing_date_is_left_to_the_service(self, mock_create, fast_api_client, fast_api_app):
        mock_create.return_value = _record()

        response = fast_api_client.post("/health_sleep", json={"total_sleep_seconds": 28800}, headers=_HEADERS)

        assert response.status_code == 201
        assert mock_create.call_args.args[1].date is None

    @patch(f"{_SERVICE}.create_health_sleep")
    def test_conflict_is_409(self, mock_create, fast_api_client, fast_api_app):
        mock_create.side_effect = core_exceptions.ConflictError("Duplicate entry error")

        response = fast_api_client.post(
            "/health_sleep", json={"date": "2024-01-15", "total_sleep_seconds": 28800}, headers=_HEADERS
        )

        assert response.status_code == 409


class TestEditHealthSleep:
    @patch(f"{_SERVICE}.edit_health_sleep")
    def test_edits(self, mock_edit, fast_api_client, fast_api_app):
        mock_edit.return_value = _record(seconds=32400)

        response = fast_api_client.put(
            "/health_sleep",
            json={"id": 1, "user_id": 1, "date": "2024-01-15", "total_sleep_seconds": 32400},
            headers=_HEADERS,
        )

        assert response.status_code == 200
        assert response.json()["total_sleep_seconds"] == 32400

    @patch(f"{_SERVICE}.edit_health_sleep")
    def test_not_found_is_404(self, mock_edit, fast_api_client, fast_api_app):
        mock_edit.side_effect = core_exceptions.NotFoundError("Health sleep not found")

        response = fast_api_client.put(
            "/health_sleep",
            json={"id": 999, "user_id": 1, "date": "2024-01-15", "total_sleep_seconds": 32400},
            headers=_HEADERS,
        )

        assert response.status_code == 404

    @patch(f"{_SERVICE}.edit_health_sleep")
    def test_another_users_record_is_403(self, mock_edit, fast_api_client, fast_api_app):
        mock_edit.side_effect = core_exceptions.PermissionDeniedError("Cannot edit health sleep for another user.")

        response = fast_api_client.put(
            "/health_sleep",
            json={"id": 1, "user_id": 2, "date": "2024-01-15", "total_sleep_seconds": 32400},
            headers=_HEADERS,
        )

        assert response.status_code == 403


class TestDeleteHealthSleep:
    @patch(f"{_SERVICE}.delete_health_sleep")
    def test_deletes(self, mock_delete, fast_api_client, fast_api_app):
        response = fast_api_client.delete("/health_sleep/1", headers=_HEADERS)

        assert response.status_code == 204
        assert mock_delete.call_args.args[:2] == (1, 1)

    @patch(f"{_SERVICE}.delete_health_sleep")
    def test_not_found_is_404(self, mock_delete, fast_api_client, fast_api_app):
        mock_delete.side_effect = core_exceptions.NotFoundError("Health sleep not found")

        response = fast_api_client.delete("/health_sleep/999", headers=_HEADERS)

        assert response.status_code == 404
