"""The gear component routes, through the production application: real authentication, handlers and database."""

import uuid
from datetime import date

import pytest

import core.config as core_config
import modules.gears.gear_components.crud as crud
from tests._factories.activities import make_activity
from tests._factories.gears import make_gear, make_gear_component
from tests._factories.users import make_user

_URL = f"{core_config.ROOT_PATH}/gear-components"
_GEARS = f"{core_config.ROOT_PATH}/gears"


@pytest.fixture
def user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created


@pytest.fixture
def other(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created


@pytest.fixture
def me(sign_in, user):
    return sign_in(user)


@pytest.fixture
def bike(committed_sessions, user):
    """A committed bike of the user."""
    with committed_sessions() as db:
        created = make_gear(db, user.id)
        db.commit()
    return created


@pytest.fixture
def make_component(committed_sessions):
    """Return a function that commits a component for a user and returns it."""

    def make(owner, gear_id, **overrides):
        with committed_sessions() as db:
            component = make_gear_component(db, owner.id, gear_id, **overrides)
            db.commit()
        return component

    return make


def _body(gear_id, **overrides):
    return {"gear_id": str(gear_id), "type": "chain", "brand": "Shimano", "model": "XT", **overrides}


def _stored(committed_sessions, owner):
    with committed_sessions() as db:
        return crud.get_gear_components_user(owner.id, db)


class TestTypes:
    def test_every_gear_type_with_a_catalogue_is_listed(self, me):
        response = me.client.get(f"{_URL}/types")

        assert response.status_code == 200
        body = response.json()
        assert {"bike", "shoes", "racquet", "windsurf"} <= set(body)
        assert "chain" in body["bike"]


class TestList:
    def test_the_users_components_are_listed_without_usage(
        self, me, user, other, bike, make_component, committed_sessions
    ):
        mine = make_component(user, bike.id)
        with committed_sessions() as db:
            theirs = make_gear(db, other.id)
            db.commit()
        make_component(other, theirs.id)

        body = me.client.get(_URL).json()

        assert [i["id"] for i in body["items"]] == [str(mine.id)]
        assert "current_distance" not in body["items"][0]
        assert "current_time" not in body["items"][0]
        assert (body["total"], body["next"]) == (1, None)

    def test_a_gears_components_carry_the_usage_of_their_window(
        self, me, user, bike, make_component, committed_sessions
    ):
        component = make_component(user, bike.id, purchase_date=date(2025, 1, 1))
        retired = make_component(user, bike.id, purchase_date=date(2024, 1, 1), retired_date=date(2024, 6, 1))
        with committed_sessions() as db:
            make_activity(db, user.id, gear_id=bike.id, distance=300, total_timer_time=30.0)
            db.commit()

        body = me.client.get(f"{_GEARS}/{bike.id}/components").json()

        usage = {i["id"]: (i["current_distance"], i["current_time"]) for i in body["items"]}
        assert usage == {str(component.id): (300.0, 30.0), str(retired.id): (0, 0)}

    def test_a_gears_components_filter_on_active(self, me, user, bike, make_component):
        make_component(user, bike.id)
        retired = make_component(user, bike.id, purchase_date=date(2024, 1, 1), retired_date=date(2024, 6, 1))

        body = me.client.get(f"{_GEARS}/{bike.id}/components", params={"active": "false"}).json()

        assert [i["id"] for i in body["items"]] == [str(retired.id)]

    def test_the_components_of_another_users_gear_are_not_listed(self, me, other, make_component, committed_sessions):
        with committed_sessions() as db:
            theirs = make_gear(db, other.id)
            db.commit()
        make_component(other, theirs.id)

        assert me.client.get(f"{_GEARS}/{theirs.id}/components").json()["items"] == []

    @pytest.mark.parametrize("path", ["", "/1/components"])
    def test_a_query_or_id_the_route_does_not_accept_is_422(self, me, path):
        url = f"{_GEARS}{path}" if path else f"{_URL}?num_records=0"

        assert me.client.get(url).status_code == 422


class TestRead:
    def test_the_component_comes_with_its_version_as_the_etag(self, me, user, bike, make_component):
        component = make_component(user, bike.id)

        response = me.client.get(f"{_URL}/{component.id}")

        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        assert response.json()["id"] == str(component.id)

    def test_a_component_that_does_not_exist_is_404(self, me):
        assert me.client.get(f"{_URL}/{uuid.uuid4()}").status_code == 404

    def test_an_id_that_is_not_a_uuid_is_422(self, me):
        assert me.client.get(f"{_URL}/1").status_code == 422


class TestCreate:
    def test_a_component_is_created_with_its_location_etag_and_expected_usage(self, me, user, bike, committed_sessions):
        response = me.client.post(_URL, json=_body(bike.id, expected_usage=5_000_000))

        assert response.status_code == 201
        body = response.json()
        assert response.headers["Location"].endswith(f"{_URL}/{body['id']}")
        assert response.headers["ETag"] == '"1"'
        assert (body["gear_id"], body["expected_usage"], body["active"]) == (str(bike.id), 5_000_000, True)
        assert "current_distance" not in body
        assert [c.id for c in _stored(committed_sessions, user)] == [uuid.UUID(body["id"])]

    def test_a_gear_the_user_does_not_have_is_404(self, me, other, committed_sessions):
        with committed_sessions() as db:
            theirs = make_gear(db, other.id)
            db.commit()

        assert me.client.post(_URL, json=_body(theirs.id)).status_code == 404
        assert me.client.post(_URL, json=_body(uuid.uuid4())).status_code == 404

    def test_a_type_that_does_not_fit_the_gear_is_400(self, me, user, bike, committed_sessions):
        response = me.client.post(_URL, json=_body(bike.id, type="laces"))

        assert response.status_code == 400
        assert _stored(committed_sessions, user) == []

    @pytest.mark.parametrize(
        "overrides",
        [{"expected_kms": 5_000_000}, {"gear_id": "not-a-uuid"}, {"gear_id": 1}, {"user_id": str(uuid.uuid4())}],
    )
    def test_a_body_the_route_does_not_accept_is_422(self, me, bike, overrides):
        assert me.client.post(_URL, json=_body(bike.id) | overrides).status_code == 422


class TestEdit:
    def test_an_edit_is_partial_and_returns_the_new_etag(self, me, user, bike, make_component, committed_sessions):
        component = make_component(user, bike.id)

        response = me.client.patch(f"{_URL}/{component.id}", json={"brand": "SRAM"}, headers={"If-Match": '"1"'})

        assert response.status_code == 200
        assert response.headers["ETag"] == '"2"'
        assert (response.json()["brand"], response.json()["model"]) == ("SRAM", "CN-HG71")
        assert _stored(committed_sessions, user)[0].brand == "SRAM"

    def test_a_retired_component_is_always_inactive(self, me, user, bike, make_component):
        component = make_component(user, bike.id, purchase_date=date(2024, 1, 1))

        response = me.client.patch(
            f"{_URL}/{component.id}",
            json={"retired_date": "2025-01-01", "active": True},
            headers={"If-Match": '"1"'},
        )

        assert (response.json()["retired_date"], response.json()["active"]) == ("2025-01-01", False)

    def test_retiring_before_the_purchase_is_400(self, me, user, bike, make_component):
        component = make_component(user, bike.id, purchase_date=date(2024, 5, 1))

        response = me.client.patch(
            f"{_URL}/{component.id}", json={"retired_date": "2024-05-01"}, headers={"If-Match": '"1"'}
        )

        assert response.status_code == 400

    def test_a_stale_edit_is_412_and_changes_nothing(self, me, user, bike, make_component, committed_sessions):
        component = make_component(user, bike.id)

        response = me.client.patch(f"{_URL}/{component.id}", json={"brand": "x"}, headers={"If-Match": '"9"'})

        assert response.status_code == 412
        assert _stored(committed_sessions, user)[0].brand == "Shimano"

    @pytest.mark.parametrize("body", [{"purchase_date": None}, {"brand": None}, {"gear_id": str(uuid.uuid4())}])
    def test_a_body_the_route_does_not_accept_is_422(self, me, user, bike, make_component, body):
        component = make_component(user, bike.id)

        assert me.client.patch(f"{_URL}/{component.id}", json=body, headers={"If-Match": '"1"'}).status_code == 422


class TestDelete:
    def test_the_component_is_deleted(self, me, user, bike, make_component, committed_sessions):
        component = make_component(user, bike.id)

        response = me.client.delete(f"{_URL}/{component.id}", headers={"If-Match": '"1"'})

        assert response.status_code == 204
        assert _stored(committed_sessions, user) == []

    def test_a_stale_delete_is_412_and_keeps_the_component(self, me, user, bike, make_component, committed_sessions):
        component = make_component(user, bike.id)

        response = me.client.delete(f"{_URL}/{component.id}", headers={"If-Match": '"9"'})

        assert response.status_code == 412
        assert len(_stored(committed_sessions, user)) == 1
