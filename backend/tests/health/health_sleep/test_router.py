from datetime import date as datetime_date
from unittest.mock import patch

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.health.health_sleep.schema as health_sleep_schema

_SERVICE = "modules.health.health_sleep.router.health_sleep_service"
_HEADERS = {"Authorization": "Bearer mock_token"}
_IF_MATCH_HEADERS = {**_HEADERS, "If-Match": '"1"'}


def _record(record_id: int = 1, day: int = 15, seconds: int = 28800) -> health_sleep_schema.HealthSleepRead:
    return health_sleep_schema.HealthSleepRead(
        updated_at="2024-01-01T00:00:00Z",
        id=record_id,
        user_id=1,
        date=datetime_date(2024, 1, day),
        total_sleep_seconds=seconds,
    )


def _item(record_id: int = 1, *, has_stages: bool = False) -> health_sleep_schema.HealthSleepListItem:
    return health_sleep_schema.HealthSleepListItem(
        updated_at="2024-01-01T00:00:00Z",
        id=record_id,
        user_id=1,
        date=datetime_date(2024, 1, 15),
        has_sleep_stages=has_stages,
    )


def _item_with(record_id: int, seconds: int) -> health_sleep_schema.HealthSleepListItem:
    return health_sleep_schema.HealthSleepListItem(
        updated_at="2024-01-01T00:00:00Z",
        id=record_id,
        user_id=1,
        date=datetime_date(2024, 1, 15),
        total_sleep_seconds=seconds,
        has_sleep_stages=False,
    )


class TestReadHealthSleepAll:
    @patch(f"{_SERVICE}.list_health_sleep")
    def test_items_carry_the_stage_flag_not_the_stages(self, mock_list, fast_api_client, fast_api_app):
        mock_list.return_value = core_pagination.Page(
            items=[_item(1, has_stages=True), _item(2, has_stages=False)], total=2, page=1, num_records=25
        )

        response = fast_api_client.get("/health_sleep", headers=_HEADERS)

        items = response.json()["items"]
        assert all("sleep_stages" not in item for item in items)
        assert [item["has_sleep_stages"] for item in items] == [True, False]

    @patch(f"{_SERVICE}.list_health_sleep")
    def test_returns_the_page_and_total(self, mock_list, fast_api_client, fast_api_app):
        mock_list.return_value = core_pagination.Page(
            items=[_item_with(1, 28800), _item_with(2, 30000)], total=2, page=1, num_records=25
        )

        response = fast_api_client.get("/health_sleep", headers=_HEADERS)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert [r["total_sleep_seconds"] for r in data["items"]] == [28800, 30000]

    @patch(f"{_SERVICE}.list_health_sleep")
    def test_empty(self, mock_list, fast_api_client, fast_api_app):
        mock_list.return_value = core_pagination.Page(items=[], total=0, page=1, num_records=25)

        response = fast_api_client.get("/health_sleep", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json()["items"] == []

    @patch(f"{_SERVICE}.list_health_sleep")
    def test_passes_pagination_and_interval_through(self, mock_list, fast_api_client, fast_api_app):
        mock_list.return_value = core_pagination.Page(items=[], total=0, page=2, num_records=10)

        response = fast_api_client.get(
            "/health_sleep?page_number=2&num_records=10&interval=last_30_days", headers=_HEADERS
        )

        assert response.status_code == 200
        args = mock_list.call_args
        assert args.args[0] == 1
        assert (args.kwargs["page_number"], args.kwargs["num_records"]) == (2, 10)
        assert args.kwargs["interval"].value == "last_30_days"
        assert args.kwargs["has_resting_heart_rate"] is None

    @patch(f"{_SERVICE}.list_health_sleep")
    def test_passes_the_resting_heart_rate_filter_through(self, mock_list, fast_api_client, fast_api_app):
        mock_list.return_value = core_pagination.Page(items=[], total=0, page=1, num_records=25)

        response = fast_api_client.get("/health_sleep?has_resting_heart_rate=true", headers=_HEADERS)

        assert response.status_code == 200
        assert mock_list.call_args.kwargs["has_resting_heart_rate"] is True


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

    @patch(f"{_SERVICE}.create_health_sleep")
    def test_an_inverted_mixed_offset_pair_is_422(self, mock_create, fast_api_client, fast_api_app):
        response = fast_api_client.post(
            "/health_sleep",
            json={
                "date": "2024-01-15",
                "sleep_start_time_gmt": "2024-01-15T22:00:00Z",
                "sleep_end_time_gmt": "2024-01-15T06:00:00",
            },
            headers=_HEADERS,
        )

        assert response.status_code == 422
        mock_create.assert_not_called()


class TestEditHealthSleep:
    @patch(f"{_SERVICE}.edit_health_sleep")
    def test_edits(self, mock_edit, fast_api_client, fast_api_app):
        mock_edit.return_value = _record(seconds=32400)

        response = fast_api_client.patch(
            "/health_sleep/1",
            json={"date": "2024-01-15", "total_sleep_seconds": 32400},
            headers={**_HEADERS, "If-Match": '"1"'},
        )

        assert response.status_code == 200
        assert response.json()["total_sleep_seconds"] == 32400

    @patch(f"{_SERVICE}.edit_health_sleep")
    def test_not_found_is_404(self, mock_edit, fast_api_client, fast_api_app):
        mock_edit.side_effect = core_exceptions.NotFoundError("Health sleep not found")

        response = fast_api_client.patch(
            "/health_sleep/999",
            json={"date": "2024-01-15", "total_sleep_seconds": 32400},
            headers={**_HEADERS, "If-Match": '"1"'},
        )

        assert response.status_code == 404


class TestDeleteHealthSleep:
    @patch(f"{_SERVICE}.delete_health_sleep")
    def test_deletes(self, mock_delete, fast_api_client, fast_api_app):
        response = fast_api_client.delete("/health_sleep/1", headers=_IF_MATCH_HEADERS)

        assert response.status_code == 204
        assert mock_delete.call_args.args[:2] == (1, 1)
        assert mock_delete.call_args.kwargs == {"if_match": '"1"'}

    @patch(f"{_SERVICE}.delete_health_sleep")
    def test_not_found_is_404(self, mock_delete, fast_api_client, fast_api_app):
        mock_delete.side_effect = core_exceptions.NotFoundError("Health sleep not found")

        response = fast_api_client.delete("/health_sleep/999", headers=_IF_MATCH_HEADERS)

        assert response.status_code == 404


class TestReadHealthSleepById:
    @patch(f"{_SERVICE}.get_health_sleep")
    def test_returns_the_record_with_its_etag(self, mock_get, fast_api_client, fast_api_app):
        mock_get.return_value = _record()

        response = fast_api_client.get("/health_sleep/1", headers=_HEADERS)

        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        assert mock_get.call_args.args[:2] == (1, 1)

    @patch(f"{_SERVICE}.get_health_sleep")
    def test_a_record_the_user_does_not_have_is_404(self, mock_get, fast_api_client, fast_api_app):
        mock_get.side_effect = core_exceptions.NotFoundError("Health sleep not found")

        response = fast_api_client.get("/health_sleep/99", headers=_HEADERS)

        assert response.status_code == 404


class TestCreateHealthSleepHeaders:
    @patch(f"{_SERVICE}.create_health_sleep")
    def test_create_names_the_record_and_its_version(self, mock_create, fast_api_client, fast_api_app):
        mock_create.return_value = _record(record_id=7)

        response = fast_api_client.post(
            "/health_sleep", json={"date": "2024-01-15", "total_sleep_seconds": 28800}, headers=_HEADERS
        )

        assert response.headers["Location"] == "/health_sleep/7"
        assert response.headers["ETag"] == '"1"'
