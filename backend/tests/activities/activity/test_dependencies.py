"""The typed request parameters reject a bad value through FastAPI's own validation (422)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions
import modules.activities.activity.dependencies as activity_dependencies


def _client() -> TestClient:
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)

    @app.get("/list")
    def list_activities(
        activity_type: activity_dependencies.ActivityTypeFilter = None,
        sort_by: activity_dependencies.SortBy = None,
        sort_order: activity_dependencies.SortOrder = None,
    ) -> dict:
        return {
            "type": activity_type,
            "sort_by": sort_by.value if sort_by else None,
            "sort_order": sort_order.value if sort_order else None,
        }

    @app.get("/{activity_id}")
    def read(activity_id: activity_dependencies.ActivityId) -> dict:
        return {"id": activity_id}

    return TestClient(app)


class TestActivityTypeFilter:
    def test_a_known_type_and_no_filter_are_accepted(self):
        client = _client()

        assert client.get("/list", params={"type": 1}).json()["type"] == 1
        assert client.get("/list").json()["type"] is None

    def test_an_unknown_type_is_a_validation_error(self):
        response = _client().get("/list", params={"type": 9999})

        assert response.status_code == 422
        assert response.json()["errors"][0]["field"] == "query.type"


class TestSortParameters:
    def test_known_sort_keys_and_directions_are_accepted(self):
        client = _client()

        for key in ("name", "distance", "average_hr"):
            assert client.get("/list", params={"sort_by": key}).status_code == 200
        assert client.get("/list", params={"sort_order": "desc"}).json()["sort_order"] == "desc"

    def test_an_unknown_sort_key_is_rejected(self):
        assert _client().get("/list", params={"sort_by": "nope"}).status_code == 422

    def test_an_unknown_sort_direction_is_rejected(self):
        assert _client().get("/list", params={"sort_order": "sideways"}).status_code == 422

    def test_every_sort_field_is_accepted(self):
        import modules.activities.activity.constants as activity_constants

        client = _client()
        assert set(activity_constants.ACTIVITY_SORT_FIELDS) == set(activity_constants.ActivitySortField)
        for key in activity_constants.ACTIVITY_SORT_FIELDS:
            assert client.get("/list", params={"sort_by": key}).status_code == 200


class TestActivityId:
    def test_a_positive_id_is_accepted(self):
        assert _client().get("/7").json() == {"id": 7}

    def test_zero_and_negative_ids_are_rejected(self):
        client = _client()

        assert client.get("/0").status_code == 422
        assert client.get("/-3").status_code == 422
