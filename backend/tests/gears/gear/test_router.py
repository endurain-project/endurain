"""The gear routes, through the production application: real authentication, scopes, handlers and database."""

import uuid

import pytest

import core.config as core_config
import core.local_pool as core_local_pool
import modules.activities.activity.models as activity_models
import modules.gears.gear.constants as gears_constants
import modules.gears.gear.crud as gears_crud
import modules.gears.gear.deletion_job_service as deletion_job_service
import modules.gears.gear.deletion_state_store as deletion_state_store
from tests._factories.activities import make_activity
from tests._factories.gears import make_gear, make_gear_component
from tests._factories.users import make_user

_URL = f"{core_config.ROOT_PATH}/gears"
_JOBS = f"{core_config.ROOT_PATH}/jobs"


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
def make_owned_gear(committed_sessions):
    """Return a function that commits a gear for a user and returns it."""

    def make(owner, **overrides):
        with committed_sessions() as db:
            gear = make_gear(db, owner.id, **overrides)
            db.commit()
        return gear

    return make


def _stored(committed_sessions, owner, gear_id):
    """Read a gear back in a new session, or ``None``."""
    with committed_sessions() as db:
        return gears_crud.get_gear_user_by_id(owner.id, gear_id, db)


@pytest.fixture
def deletion_pool(monkeypatch):
    """Replace the module's in-process deletion pool with one of its own, which the test drains before it reads."""
    pool = core_local_pool.BoundedPool("gear-deletion-test", workers=1, max_pending=2)
    monkeypatch.setattr(deletion_job_service, "_pool", pool)
    yield pool
    pool.shutdown(wait=True)


class TestList:
    def test_the_users_gears_come_ordered_by_nickname_in_a_page_envelope(self, me, user, other, make_owned_gear):
        make_owned_gear(user, nickname="B bike", brand="Trek")
        make_owned_gear(user, nickname="A bike")
        make_owned_gear(other, nickname="Theirs")

        body = me.client.get(_URL).json()

        assert [item["nickname"] for item in body["items"]] == ["A bike", "B bike"]
        assert (body["total"], body["page"], body["next"]) == (2, 1, None)
        assert body["items"][1]["brand"] == "Trek"
        assert body["items"][1]["gear_type"] == "bike"

    def test_the_filters_narrow_the_page_and_the_total(self, me, user, make_owned_gear):
        make_owned_gear(user, nickname="Road", active=True)
        make_owned_gear(user, nickname="Gravel", active=False)
        make_owned_gear(user, nickname="Trail shoes", gear_type="shoes")

        by_active = me.client.get(_URL, params={"active": "false"}).json()
        by_type = me.client.get(_URL, params={"gear_type": "shoes"}).json()
        by_text = me.client.get(_URL, params={"nickname_contains": "RAV"}).json()

        assert [i["nickname"] for i in by_active["items"]] == ["Gravel"]
        assert [i["nickname"] for i in by_type["items"]] == ["Trail shoes"]
        assert (by_text["total"], [i["nickname"] for i in by_text["items"]]) == (1, ["Gravel"])

    def test_a_page_holds_its_slice_and_names_the_next_one(self, me, user, make_owned_gear):
        for name in ("A", "B", "C"):
            make_owned_gear(user, nickname=name)

        first = me.client.get(_URL, params={"page_number": 1, "num_records": 2}).json()
        last = me.client.get(_URL, params={"page_number": 2, "num_records": 2}).json()

        assert ([i["nickname"] for i in first["items"]], first["total"], first["next"]) == (["A", "B"], 3, 2)
        assert ([i["nickname"] for i in last["items"]], last["next"]) == (["C"], None)

    @pytest.mark.parametrize(
        "params",
        [{"num_records": 201}, {"page_number": 0}, {"gear_type": "99"}, {"gear_type": "1"}, {"gear_type": "bicycle"}],
    )
    def test_a_query_the_route_does_not_accept_is_422(self, me, params):
        assert me.client.get(_URL, params=params).status_code == 422


class TestRead:
    def test_the_gear_comes_with_its_totals_and_its_version_as_the_etag(
        self, me, user, make_owned_gear, committed_sessions
    ):
        gear = make_owned_gear(user, initial_distance=1000.0)
        with committed_sessions() as db:
            make_activity(db, user.id, gear_id=gear.id, distance=500, total_timer_time=60.0)
            make_gear_component(db, user.id, gear.id, purchase_value="12.50")
            db.commit()

        response = me.client.get(f"{_URL}/{gear.id}")

        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        body = response.json()
        assert (body["total_distance"], body["total_time"], body["total_components_cost"]) == (1500.0, 60.0, "12.50")

    def test_a_gear_that_does_not_exist_is_404(self, me):
        assert me.client.get(f"{_URL}/{uuid.uuid4()}").status_code == 404

    @pytest.mark.parametrize("gear_id", ["not-a-uuid", "0", "1"])
    def test_an_id_that_is_not_a_uuid_is_422(self, me, gear_id):
        assert me.client.get(f"{_URL}/{gear_id}").status_code == 422


class TestCreate:
    def test_a_gear_is_created_for_the_caller_with_its_location_and_etag(self, me, user, committed_sessions):
        response = me.client.post(_URL, json={"nickname": "  New Bike ", "gear_type": "bike", "brand": "Trek"})

        assert response.status_code == 201
        body = response.json()
        assert response.headers["Location"].endswith(f"{_URL}/{body['id']}")
        assert response.headers["ETag"] == '"1"'
        assert (body["nickname"], body["user_id"], body["version"], body["active"]) == (
            "New Bike",
            str(user.id),
            1,
            True,
        )
        assert _stored(committed_sessions, user, uuid.UUID(body["id"])).brand == "Trek"

    def test_a_nickname_the_user_has_in_another_case_is_409(self, me, user, make_owned_gear):
        make_owned_gear(user, nickname="Road Bike")

        response = me.client.post(_URL, json={"nickname": "ROAD bike", "gear_type": "bike"})

        assert response.status_code == 409

    def test_another_users_nickname_is_free(self, me, other, make_owned_gear):
        make_owned_gear(other, nickname="Road Bike")

        assert me.client.post(_URL, json={"nickname": "Road Bike", "gear_type": "bike"}).status_code == 201

    @pytest.mark.parametrize(
        "body",
        [
            {"nickname": "x", "gear_type": "bike", "strava_gear_id": "b1"},
            {"nickname": "x", "gear_type": "bike", "garminconnect_gear_id": "g1"},
            {"nickname": "x", "gear_type": "bike", "user_id": str(uuid.uuid4())},
            {"nickname": "   ", "gear_type": "bike"},
            {"nickname": "x", "gear_type": 1},
            {"gear_type": "bike"},
        ],
    )
    def test_a_body_the_route_does_not_accept_is_422(self, me, body):
        assert me.client.post(_URL, json=body).status_code == 422


class TestEdit:
    def test_an_edit_is_partial_bumps_the_version_and_returns_the_new_etag(
        self, me, user, make_owned_gear, committed_sessions
    ):
        gear = make_owned_gear(user, brand="Trek", purchase_value="10.00")

        response = me.client.patch(
            f"{_URL}/{gear.id}", json={"nickname": "Updated", "purchase_value": None}, headers={"If-Match": '"1"'}
        )

        assert response.status_code == 200
        assert response.headers["ETag"] == '"2"'
        body = response.json()
        assert (body["nickname"], body["brand"], body["purchase_value"], body["version"]) == (
            "Updated",
            "Trek",
            None,
            2,
        )
        assert _stored(committed_sessions, user, gear.id).nickname == "Updated"

    def test_a_stale_edit_is_412_and_changes_nothing(self, me, user, make_owned_gear, committed_sessions):
        gear = make_owned_gear(user)

        response = me.client.patch(f"{_URL}/{gear.id}", json={"brand": "x"}, headers={"If-Match": '"7"'})

        assert response.status_code == 412
        assert _stored(committed_sessions, user, gear.id).brand is None

    def test_an_edit_onto_a_taken_nickname_is_409(self, me, user, make_owned_gear):
        make_owned_gear(user, nickname="Taken")
        mine = make_owned_gear(user, nickname="Mine")

        response = me.client.patch(f"{_URL}/{mine.id}", json={"nickname": "taken"}, headers={"If-Match": '"1"'})

        assert response.status_code == 409

    def test_a_type_change_blocked_by_components_is_a_typed_409(self, me, user, make_owned_gear, committed_sessions):
        gear = make_owned_gear(user)
        with committed_sessions() as db:
            make_gear_component(db, user.id, gear.id, type="chain")
            db.commit()

        response = me.client.patch(f"{_URL}/{gear.id}", json={"gear_type": "shoes"}, headers={"If-Match": '"1"'})

        assert response.status_code == 409
        assert response.json()["type"] == "urn:endurain:error:components-outside-gear-type"
        assert _stored(committed_sessions, user, gear.id).gear_type.value == "bike"

    @pytest.mark.parametrize("body", [{"nickname": None}, {"strava_gear_id": "b1"}, {"acquired_on": None}])
    def test_a_body_the_route_does_not_accept_is_422(self, me, user, make_owned_gear, body):
        gear = make_owned_gear(user)

        assert me.client.patch(f"{_URL}/{gear.id}", json=body, headers={"If-Match": '"1"'}).status_code == 422


class TestDelete:
    def test_the_deletion_is_queued_and_the_job_unassigns_the_activities_and_deletes_the_gear(
        self, me, user, make_owned_gear, committed_sessions, deletion_pool
    ):
        gear = make_owned_gear(user)
        with committed_sessions() as db:
            activity = make_activity(db, user.id, gear_id=gear.id)
            db.commit()

        response = me.client.delete(f"{_URL}/{gear.id}", headers={"If-Match": '"1"'})

        assert response.status_code == 202
        job = response.json()
        assert (job["kind"], job["status"]) == (gears_constants.DELETION_JOB, "queued")
        assert response.headers["Content-Location"].endswith(f"{_JOBS}/{job['id']}")
        assert response.headers["Retry-After"] == str(gears_constants.DELETION_POLL_SECONDS)
        deletion_pool.shutdown(wait=True)
        polled = me.client.get(f"{_JOBS}/{job['id']}").json()
        assert polled["status"] == "succeeded"
        assert _stored(committed_sessions, user, gear.id) is None
        with committed_sessions() as db:
            assert db.get(activity_models.Activity, activity.id).gear_id is None

    def test_a_stale_delete_is_412_and_queues_nothing(self, me, user, make_owned_gear, committed_sessions):
        gear = make_owned_gear(user)

        response = me.client.delete(f"{_URL}/{gear.id}", headers={"If-Match": '"9"'})

        assert response.status_code == 412
        assert "Content-Location" not in response.headers
        assert _stored(committed_sessions, user, gear.id) is not None

    def test_a_gear_that_does_not_exist_is_404(self, me):
        assert me.client.delete(f"{_URL}/{uuid.uuid4()}", headers={"If-Match": '"1"'}).status_code == 404

    def test_a_second_delete_while_one_is_pending_is_409_naming_the_job(
        self, me, user, make_owned_gear, _publish_local_platform, committed_sessions
    ):
        gear = make_owned_gear(user)
        states = deletion_state_store.GearDeletionStateStore(_publish_local_platform.state)
        running = states.begin(gear.id, user.id, conflict="x")

        response = me.client.delete(f"{_URL}/{gear.id}", headers={"If-Match": '"1"'})

        assert response.status_code == 409
        assert response.headers["Content-Location"].endswith(f"{_JOBS}/{running.id}")
        assert _stored(committed_sessions, user, gear.id) is not None
