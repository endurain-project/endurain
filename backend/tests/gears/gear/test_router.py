from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.database as core_db
import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.dependencies as auth_deps
import modules.gears.gear.router as router
import modules.gears.gear.schema as schema

_HEADERS = {"Authorization": "Bearer x"}


@pytest.fixture
def client(mock_db):
    app = FastAPI()
    app.include_router(router.router, prefix="/gears")
    core_exceptions.register_exception_handlers(app)
    app.dependency_overrides[auth_deps.check_scopes] = lambda: None
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: 1
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return TestClient(app)


def _read(**overrides) -> schema.GearRead:
    return schema.GearRead(**{"id": 1, "user_id": 1, "nickname": "Bike", "gear_type": 1, **overrides})


class TestList:
    @patch("modules.gears.gear.service.list_gears")
    def test_passes_the_query_to_the_service(self, mock_list, client, mock_db):
        mock_list.return_value = core_pagination.Page.build([_read()], 1, 2, 5)

        response = client.get(
            "/gears?page_number=2&num_records=5&show_inactive=false&gear_type=1&nickname_contains=bike",
            headers=_HEADERS,
        )

        assert response.status_code == 200
        assert response.json()["total"] == 1
        mock_list.assert_called_once_with(
            1,
            mock_db,
            page_number=2,
            num_records=5,
            show_inactive=False,
            gear_type=schema.GearType.BIKE,
            nickname_contains="bike",
        )

    @patch("modules.gears.gear.service.list_gears")
    def test_an_unpaged_request_gets_the_default_page(self, mock_list, client, mock_db):
        mock_list.return_value = core_pagination.Page.build([], 0, 1, core_pagination.DEFAULT_NUM_RECORDS)

        client.get("/gears", headers=_HEADERS)

        mock_list.assert_called_once_with(
            1,
            mock_db,
            page_number=1,
            num_records=core_pagination.DEFAULT_NUM_RECORDS,
            show_inactive=None,
            gear_type=None,
            nickname_contains=None,
        )

    def test_an_oversized_page_is_rejected(self, client):
        response = client.get(f"/gears?num_records={core_pagination.MAX_NUM_RECORDS + 1}", headers=_HEADERS)

        assert response.status_code == 422

    def test_an_unknown_type_is_rejected(self, client):
        assert client.get("/gears?gear_type=99", headers=_HEADERS).status_code == 422


class TestReadById:
    @patch("modules.gears.gear.service.read_gear_detail")
    def test_the_version_is_sent_as_the_etag(self, mock_detail, client):
        mock_detail.return_value = schema.GearDetailRead(**_read(version=7).model_dump())

        assert client.get("/gears/1", headers=_HEADERS).headers["ETag"] == '"7"'

    @patch("modules.gears.gear.service.read_gear_detail")
    def test_unknown_gear_is_not_found(self, mock_detail, client):
        mock_detail.side_effect = core_exceptions.NotFoundError("Gear not found")

        assert client.get("/gears/999", headers=_HEADERS).status_code == 404

    def test_a_non_positive_id_is_rejected(self, client):
        assert client.get("/gears/0", headers=_HEADERS).status_code == 422


class TestWrites:
    @patch("modules.gears.gear.service.create_gear")
    def test_create(self, mock_create, client):
        mock_create.return_value = _read(nickname="New Bike")

        response = client.post("/gears", json={"nickname": "New Bike", "gear_type": 1}, headers=_HEADERS)

        assert response.status_code == 201

    @patch("modules.gears.gear.service.create_gear")
    def test_create_conflict_is_409(self, mock_create, client):
        mock_create.side_effect = core_exceptions.ConflictError("exists")

        response = client.post("/gears", json={"nickname": "New Bike", "gear_type": 1}, headers=_HEADERS)

        assert response.status_code == 409

    @patch("modules.gears.gear.service.edit_gear")
    def test_edit_is_partial_and_returns_the_etag(self, mock_edit, client, mock_db):
        mock_edit.return_value = _read(nickname="Updated", version=4)

        response = client.patch("/gears/1", json={"nickname": "Updated"}, headers={**_HEADERS, "If-Match": '"3"'})

        assert response.status_code == 200
        assert response.json()["nickname"] == "Updated"
        assert response.headers["ETag"] == '"4"'
        assert mock_edit.call_args.kwargs == {"if_match": '"3"'}

    @patch("modules.gears.gear.service.edit_gear")
    def test_an_edit_without_if_match_is_428(self, mock_edit, client):
        assert client.patch("/gears/1", json={"brand": "x"}, headers=_HEADERS).status_code == 428
        mock_edit.assert_not_called()

    @patch("modules.gears.gear.service.edit_gear")
    def test_a_stale_edit_is_412(self, mock_edit, client):
        mock_edit.side_effect = core_exceptions.PreconditionFailedError("stale")

        assert client.patch("/gears/1", json={"brand": "x"}, headers={**_HEADERS, "If-Match": '"1"'}).status_code == 412

    def test_an_edit_cannot_clear_a_required_field_or_set_a_provider_id(self, client):
        assert (
            client.patch("/gears/1", json={"nickname": None}, headers={**_HEADERS, "If-Match": '"1"'}).status_code
            == 422
        )
        assert (
            client.patch("/gears/1", json={"strava_gear_id": "b1"}, headers={**_HEADERS, "If-Match": '"1"'}).status_code
            == 422
        )

    @patch("modules.gears.gear.service.delete_gear")
    def test_delete(self, mock_delete, client, mock_db):
        response = client.delete("/gears/1", headers={**_HEADERS, "If-Match": '"3"'})

        assert response.status_code == 204
        mock_delete.assert_called_once_with(1, 1, mock_db, if_match='"3"')

    @patch("modules.gears.gear.service.delete_gear")
    def test_delete_without_if_match_is_428(self, mock_delete, client):
        assert client.delete("/gears/1", headers=_HEADERS).status_code == 428
        mock_delete.assert_not_called()

    @patch("modules.gears.gear.service.delete_gear")
    def test_a_stale_delete_is_412(self, mock_delete, client):
        mock_delete.side_effect = core_exceptions.PreconditionFailedError("stale")

        assert client.delete("/gears/1", headers={**_HEADERS, "If-Match": '"1"'}).status_code == 412

    @patch("modules.gears.gear.service.delete_gear")
    def test_delete_of_a_missing_gear_is_404(self, mock_delete, client):
        mock_delete.side_effect = core_exceptions.NotFoundError("Gear not found")

        assert client.delete("/gears/1", headers={**_HEADERS, "If-Match": '"1"'}).status_code == 404
