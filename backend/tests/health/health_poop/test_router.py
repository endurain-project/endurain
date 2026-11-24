"""The bowel movement routes, through the production application: real authentication, scopes and database."""

import uuid
from datetime import UTC, datetime, timedelta

import jasil.runtime as platform_runtime
import pytest

import core.config as core_config
import modules.health.health_poop.models as health_poop_models
from tests._factories.health import make_health_poop
from tests._factories.users import make_user

_URL = f"{core_config.ROOT_PATH}/health/poop"
_NOW = datetime(2025, 3, 10, 12, 0, tzinfo=UTC)
_AT = datetime(2025, 3, 1, 9, 0, tzinfo=UTC)
_ANY_ID = "6f1c2a4e-3b7d-4c58-9a10-5d2e8b7c9f01"


@pytest.fixture(autouse=True)
def now():
    """Stand the platform clock at :data:`_NOW`."""
    platform_runtime.get_active_platform().clock.moment = _NOW


def _stored(committed_sessions, record_id):
    """Read a record back in a new session, detached, or ``None`` when it is gone."""
    with committed_sessions() as db:
        row = db.get(health_poop_models.HealthPoop, record_id)
        if row is not None:
            db.expunge(row)
        return row


@pytest.fixture
def user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db, timezone="UTC")
        db.commit()
    return created


@pytest.fixture
def other(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db, timezone="UTC")
        db.commit()
    return created


@pytest.fixture
def me(sign_in, user):
    return sign_in(user)


@pytest.fixture
def make_record(committed_sessions):
    """Return a function that commits a record for a user and returns it."""

    def make(owner, **overrides):
        with committed_sessions() as db:
            record = make_health_poop(db, owner.id, **overrides)
            db.commit()
        return record

    return make


class TestList:
    def test_the_users_records_come_newest_first_in_a_page_envelope(self, me, user, make_record):
        old = make_record(user, date_time=_AT)
        new = make_record(user, date_time=_AT + timedelta(days=2), bristol_type="type_3", color="brown", notes="n")

        response = me.client.get(_URL)

        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body["items"]] == [str(new.id), str(old.id)]
        assert (body["total"], body["page"], body["num_records"], body["next"]) == (2, 1, 25, None)
        assert body["items"][0] == {
            "id": str(new.id),
            "user_id": str(user.id),
            "date_time": "2025-03-03T09:00:00Z",
            "bristol_type": "type_3",
            "color": "brown",
            "notes": "n",
            "source": "manual",
            "version": 1,
            "updated_at": body["items"][0]["updated_at"],
        }

    def test_another_users_records_are_not_listed(self, me, other, make_record):
        make_record(other)

        assert me.client.get(_URL).json()["total"] == 0

    def test_a_page_holds_its_slice_the_range_is_inclusive_and_an_interval_looks_back_from_today(
        self, me, user, make_record
    ):
        for day in range(1, 6):
            make_record(user, date_time=datetime(2025, 3, day, 9, 0, tzinfo=UTC))

        page = me.client.get(_URL, params={"page_number": 2, "num_records": 2}).json()
        ranged = me.client.get(_URL, params={"start_date": "2025-03-02", "end_date": "2025-03-04"}).json()
        windowed = me.client.get(_URL, params={"interval": "last_7_days"}).json()

        assert ([i["date_time"][:10] for i in page["items"]], page["total"], page["next"]) == (
            ["2025-03-03", "2025-03-02"],
            5,
            3,
        )
        assert ranged["total"] == 3
        assert windowed["total"] == 3  # the 3rd to the 5th: the window opens seven days before the 10th

    @pytest.mark.parametrize(
        "params",
        [{"page_number": 0}, {"num_records": 201}, {"interval": "last_century"}, {"start_date": "x"}],
    )
    def test_a_query_the_route_does_not_accept_is_422(self, me, params):
        assert me.client.get(_URL, params=params).status_code == 422


class TestRead:
    def test_the_record_comes_with_its_version_as_the_etag(self, me, user, make_record):
        record = make_record(user, notes="read me")

        response = me.client.get(f"{_URL}/{record.id}")

        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        assert (response.json()["id"], response.json()["notes"]) == (str(record.id), "read me")

    def test_a_record_the_user_does_not_have_is_404(self, me):
        assert me.client.get(f"{_URL}/{uuid.uuid4()}").status_code == 404


class TestChart:
    def test_the_response_counts_the_movements_of_each_day(self, me, user, make_record):
        make_record(user, date_time=_NOW)
        make_record(user, date_time=_NOW - timedelta(hours=3))
        make_record(user, date_time=_NOW - timedelta(days=1))

        response = me.client.get(f"{_URL}/chart", params={"interval": "last_7_days"})

        assert response.status_code == 200
        body = response.json()
        assert body["bucket"] == "day"
        assert [(p["date"], p["value"]) for p in body["points"]] == [("2025-03-09", 1.0), ("2025-03-10", 2.0)]

    def test_another_users_movements_are_not_charted(self, me, other, make_record):
        make_record(other, date_time=_NOW)

        assert me.client.get(f"{_URL}/chart").json()["points"] == []


class TestCreate:
    def test_the_record_is_stored_and_answered_with_its_location_and_version(self, me, user, committed_sessions):
        response = me.client.post(
            _URL, json={"date_time": "2025-03-01T09:00:00+01:00", "bristol_type": "type_4", "notes": "ok"}
        )

        assert response.status_code == 201
        body = response.json()
        assert response.headers["Location"] == f"{_URL}/{body['id']}"
        assert response.headers["ETag"] == '"1"'
        assert (body["user_id"], body["date_time"], body["bristol_type"], body["source"], body["version"]) == (
            str(user.id),
            "2025-03-01T08:00:00Z",
            "type_4",
            "manual",
            1,
        )
        row = _stored(committed_sessions, uuid.UUID(body["id"]))
        assert (row.user_id, row.bristol_type, row.notes) == (user.id, 4, "ok")
        assert me.client.get(response.headers["Location"]).json() == body

    def test_several_records_may_share_a_day(self, me):
        for _ in range(2):
            assert me.client.post(_URL, json={"date_time": "2025-03-01T09:00:00Z"}).status_code == 201

        assert me.client.get(_URL).json()["total"] == 2

    def test_a_moment_after_the_users_today_is_400(self, me):
        response = me.client.post(_URL, json={"date_time": "2025-03-12T09:00:00Z"})

        assert response.status_code == 400

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"date_time": "2025-03-01T09:00:00"},
            {"date_time": "2025-03-01"},
            {"date_time": "2025-03-01T09:00:00Z", "bristol_type": "type_9"},
            {"date_time": "2025-03-01T09:00:00Z", "bristol_type": 4},
            {"date_time": "2025-03-01T09:00:00Z", "color": "purple"},
            {"date_time": "2025-03-01T09:00:00Z", "notes": "x" * 501},
        ],
    )
    def test_a_body_the_schema_refuses_is_422_and_nothing_is_stored(self, me, body):
        assert me.client.post(_URL, json=body).status_code == 422
        assert me.client.get(_URL).json()["total"] == 0

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("id", _ANY_ID),
            ("user_id", _ANY_ID),
            ("version", 5),
            ("updated_at", "2020-01-01T00:00:00Z"),
            ("source", "x"),
        ],
    )
    def test_a_field_the_server_owns_is_422(self, me, field, value):
        response = me.client.post(_URL, json={"date_time": "2025-03-01T09:00:00Z", field: value})

        assert response.status_code == 422
        assert me.client.get(_URL).json()["total"] == 0


class TestEdit:
    @pytest.fixture
    def record(self, user, make_record):
        return make_record(user, date_time=_AT, notes="before", bristol_type="type_2")

    def _patch(self, client, record_id, body, *, if_match='"1"'):
        headers = {} if if_match is None else {"If-Match": if_match}
        return client.patch(f"{_URL}/{record_id}", json=body, headers=headers)

    def test_the_change_is_applied_and_the_version_and_etag_move_on(self, me, record, committed_sessions):
        response = self._patch(me.client, record.id, {"notes": "after"})

        assert response.status_code == 200
        assert response.headers["ETag"] == '"2"'
        body = response.json()
        assert (body["notes"], body["bristol_type"], body["date_time"], body["version"]) == (
            "after",
            "type_2",
            "2025-03-01T09:00:00Z",
            2,
        )
        row = _stored(committed_sessions, record.id)
        assert (row.notes, row.version) == ("after", 2)

    def test_an_optional_field_is_cleared_by_null(self, me, record):
        assert self._patch(me.client, record.id, {"notes": None}).json()["notes"] is None

    def test_the_old_etag_no_longer_lets_an_edit_through(self, me, record):
        assert self._patch(me.client, record.id, {"notes": "a"}).status_code == 200

        assert self._patch(me.client, record.id, {"notes": "b"}).status_code == 412

    def test_without_if_match_the_edit_is_428_and_nothing_changes(self, me, record, committed_sessions):
        assert self._patch(me.client, record.id, {"notes": "x"}, if_match=None).status_code == 428
        assert _stored(committed_sessions, record.id).notes == "before"

    def test_another_users_record_is_404_and_stays_as_it_was(self, sign_in, other, record, committed_sessions):
        response = self._patch(sign_in(other).client, record.id, {"notes": "mine"})

        assert response.status_code == 404
        assert _stored(committed_sessions, record.id).notes == "before"

    def test_a_moment_after_the_users_today_is_400_and_the_record_keeps_its_time(self, me, record, committed_sessions):
        response = self._patch(me.client, record.id, {"date_time": "2025-03-12T09:00:00Z"})

        assert response.status_code == 400
        assert _stored(committed_sessions, record.id).date_time == _AT

    @pytest.mark.parametrize(
        "body", [{"date_time": None}, {"bristol_type": "type_9"}, {"id": _ANY_ID}, {"source": "garmin"}]
    )
    def test_a_body_the_schema_refuses_is_422_and_nothing_changes(self, me, record, committed_sessions, body):
        assert self._patch(me.client, record.id, body).status_code == 422
        assert _stored(committed_sessions, record.id).version == 1


class TestDelete:
    @pytest.fixture
    def record(self, user, make_record):
        return make_record(user)

    def test_the_record_is_deleted_with_no_body_and_is_gone_afterwards(self, me, record, committed_sessions):
        response = me.client.delete(f"{_URL}/{record.id}", headers={"If-Match": '"1"'})

        assert (response.status_code, response.content) == (204, b"")
        assert _stored(committed_sessions, record.id) is None
        assert me.client.get(f"{_URL}/{record.id}").status_code == 404

    def test_a_stale_version_is_412_and_the_record_stays(self, me, record, committed_sessions):
        assert me.client.delete(f"{_URL}/{record.id}", headers={"If-Match": '"9"'}).status_code == 412
        assert _stored(committed_sessions, record.id) is not None

    def test_another_users_record_is_404_and_stays(self, sign_in, other, record, committed_sessions):
        response = sign_in(other).client.delete(f"{_URL}/{record.id}", headers={"If-Match": '"1"'})

        assert response.status_code == 404
        assert _stored(committed_sessions, record.id) is not None
