from datetime import date as datetime_date
from unittest.mock import patch

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.health.health_steps.schema as health_steps_schema

_SERVICE = "modules.health.health_steps.router.health_steps_service"
_HEADERS = {"Authorization": "Bearer mock_token"}


def _record(record_id: int = 1, day: int = 15, steps: int = 10000) -> health_steps_schema.HealthStepsRead:
    return health_steps_schema.HealthStepsRead(id=record_id, user_id=1, date=datetime_date(2024, 1, day), steps=steps)


class TestReadHealthStepsAll:
    @patch(f"{_SERVICE}.list_health_steps")
    def test_returns_the_page_and_total(self, mock_list, fast_api_client, fast_api_app):
        mock_list.return_value = core_pagination.Page(
            items=[_record(1, 15, 10000), _record(2, 16, 12000)], total=2, page=1, num_records=25
        )

        response = fast_api_client.get("/health_steps", headers=_HEADERS)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert [r["steps"] for r in data["items"]] == [10000, 12000]

    @patch(f"{_SERVICE}.list_health_steps")
    def test_empty(self, mock_list, fast_api_client, fast_api_app):
        mock_list.return_value = core_pagination.Page(items=[], total=0, page=1, num_records=25)

        response = fast_api_client.get("/health_steps", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json()["items"] == []

    @patch(f"{_SERVICE}.list_health_steps")
    def test_passes_pagination_and_interval_through(self, mock_list, fast_api_client, fast_api_app):
        mock_list.return_value = core_pagination.Page(items=[], total=0, page=2, num_records=10)

        response = fast_api_client.get(
            "/health_steps?page_number=2&num_records=10&interval=last_30_days", headers=_HEADERS
        )

        assert response.status_code == 200
        args = mock_list.call_args
        assert args.args[0] == 1
        assert (args.kwargs["page_number"], args.kwargs["num_records"]) == (2, 10)
        assert args.kwargs["interval"].value == "last_30_days"


class TestCreateHealthSteps:
    @patch(f"{_SERVICE}.create_health_steps")
    def test_creates(self, mock_create, fast_api_client, fast_api_app):
        mock_create.return_value = _record(steps=9000)

        response = fast_api_client.post("/health_steps", json={"date": "2024-01-15", "steps": 9000}, headers=_HEADERS)

        assert response.status_code == 201
        assert response.json()["steps"] == 9000

    @patch(f"{_SERVICE}.create_health_steps")
    def test_conflict_is_409(self, mock_create, fast_api_client, fast_api_app):
        mock_create.side_effect = core_exceptions.ConflictError("Duplicate entry error")

        response = fast_api_client.post("/health_steps", json={"date": "2024-01-15", "steps": 9000}, headers=_HEADERS)

        assert response.status_code == 409


class TestEditHealthSteps:
    @patch(f"{_SERVICE}.edit_health_steps")
    def test_edits(self, mock_edit, fast_api_client, fast_api_app):
        mock_edit.return_value = _record(steps=11000)

        response = fast_api_client.patch(
            "/health_steps/1",
            json={"date": "2024-01-15", "steps": 11000},
            headers={**_HEADERS, "If-Match": '"1"'},
        )

        assert response.status_code == 200
        assert response.json()["steps"] == 11000

    @patch(f"{_SERVICE}.edit_health_steps")
    def test_not_found_is_404(self, mock_edit, fast_api_client, fast_api_app):
        mock_edit.side_effect = core_exceptions.NotFoundError("Health steps not found")

        response = fast_api_client.patch(
            "/health_steps/999",
            json={"date": "2024-01-15", "steps": 11000},
            headers={**_HEADERS, "If-Match": '"1"'},
        )

        assert response.status_code == 404


class TestDeleteHealthSteps:
    @patch(f"{_SERVICE}.delete_health_steps")
    def test_deletes(self, mock_delete, fast_api_client, fast_api_app):
        response = fast_api_client.delete("/health_steps/1", headers=_HEADERS)

        assert response.status_code == 204
        assert mock_delete.call_args.args[:2] == (1, 1)

    @patch(f"{_SERVICE}.delete_health_steps")
    def test_not_found_is_404(self, mock_delete, fast_api_client, fast_api_app):
        mock_delete.side_effect = core_exceptions.NotFoundError("Health steps not found")

        response = fast_api_client.delete("/health_steps/999", headers=_HEADERS)

        assert response.status_code == 404
