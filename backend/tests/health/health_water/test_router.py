"""The water intake routes, through the production application: real authentication, scopes, handlers and database."""

import uuid
from datetime import date, timedelta

import pytest

import core.config as core_config
import core.timezone as core_timezone
import modules.health.health_water.models as health_water_models
from tests._factories.health import make_health_water
from tests._factories.users import make_user

_URL = f"{core_config.ROOT_PATH}/health/water"
_DAY = date(2025, 3, 10)
_ANY_ID = "6f1c2a4e-3b7d-4c58-9a10-5d2e8b7c9f01"


def _today() -> date:
    """The user's today: the tests' users are on UTC, and the code reads the day from the platform clock."""
    return core_timezone.today_in("UTC")


def _stored(committed_sessions, record_id):
    """Read a record back in a new session, detached, or ``None`` when it is gone."""
    with committed_sessions() as db:
        row = db.get(health_water_models.HealthWater, record_id)
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
            record = make_health_water(db, owner.id, **overrides)
            db.commit()
        return record

    return make


class TestList:
    def test_the_users_records_come_newest_first_in_a_page_envelope(self, me, user, make_record):
        old = make_record(user, date=date(2025, 3, 1), amount_ml=500.0)
        new = make_record(user, date=date(2025, 3, 9), amount_ml=900.0)

        response = me.client.get(_URL)

        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body["items"]] == [str(new.id), str(old.id)]
        assert (body["total"], body["page"], body["num_records"], body["next"]) == (2, 1, 25, None)
        assert body["items"][0] == {
            "id": str(new.id),
            "user_id": str(user.id),
            "date": "2025-03-09",
            "amount_ml": 900.0,
            "source": "manual",
            "version": 1,
            "updated_at": body["items"][0]["updated_at"],
        }

    def test_another_users_records_are_not_listed(self, me, other, make_record):
        make_record(other)

        body = me.client.get(_URL).json()

        assert (body["items"], body["total"]) == ([], 0)

    def test_a_page_holds_its_slice_and_names_the_next_one(self, me, user, make_record):
        for day in range(1, 6):
            make_record(user, date=date(2025, 3, day))

        first = me.client.get(_URL, params={"page_number": 1, "num_records": 2}).json()
        last = me.client.get(_URL, params={"page_number": 3, "num_records": 2}).json()

        assert ([i["date"] for i in first["items"]], first["total"], first["next"]) == (
            ["2025-03-05", "2025-03-04"],
            5,
            2,
        )
        assert ([i["date"] for i in last["items"]], last["next"]) == (["2025-03-01"], None)

    def test_the_date_range_is_inclusive_and_an_interval_looks_back_from_the_users_today(self, me, user, make_record):
        for day in range(1, 6):
            make_record(user, date=date(2025, 3, day))
        recent = make_record(user, date=_today() - timedelta(days=2))

        ranged = me.client.get(_URL, params={"start_date": "2025-03-02", "end_date": "2025-03-04"}).json()
        windowed = me.client.get(_URL, params={"interval": "last_7_days"}).json()

        assert [i["date"] for i in ranged["items"]] == ["2025-03-04", "2025-03-03", "2025-03-02"]
        assert [i["id"] for i in windowed["items"]] == [str(recent.id)]

    @pytest.mark.parametrize(
        "params",
        [
            {"page_number": 0},
            {"num_records": 201},
            {"interval": "last_century"},
            {"start_date": "2025-03-05", "end_date": "2025-03-01"},
        ],
    )
    def test_a_query_the_route_does_not_accept_is_422(self, me, params):
        assert me.client.get(_URL, params=params).status_code == 422


class TestRead:
    def test_the_record_comes_with_its_version_as_the_etag(self, me, user, make_record):
        record = make_record(user, date=_DAY, amount_ml=900.0)

        response = me.client.get(f"{_URL}/{record.id}")

        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        assert (response.json()["id"], response.json()["amount_ml"]) == (str(record.id), 900.0)

    def test_a_record_the_user_does_not_have_is_404(self, me):
        assert me.client.get(f"{_URL}/{uuid.uuid4()}").status_code == 404


class TestChart:
    def test_the_response_is_one_averaged_point_per_day_with_a_value(self, me, user, make_record):
        make_record(user, date=_today(), amount_ml=500.0)
        make_record(user, date=_today() - timedelta(days=1), amount_ml=900.0)

        response = me.client.get(f"{_URL}/chart", params={"interval": "last_7_days"})

        assert response.status_code == 200
        body = response.json()
        assert body["bucket"] == "day"
        assert [(p["date"], p["value"]) for p in body["points"]] == [
            ((_today() - timedelta(days=1)).isoformat(), 900.0),
            (_today().isoformat(), 500.0),
        ]

    def test_another_users_records_are_not_charted(self, me, other, make_record):
        make_record(other, date=_today())

        assert me.client.get(f"{_URL}/chart").json()["points"] == []


class TestCreate:
    def test_the_record_is_stored_and_answered_with_its_location_and_version(self, me, user, committed_sessions):
        response = me.client.post(_URL, json={"date": "2025-03-10", "amount_ml": 500.0})

        assert response.status_code == 201
        body = response.json()
        assert response.headers["Location"] == f"{_URL}/{body['id']}"
        assert response.headers["ETag"] == '"1"'
        assert (body["user_id"], body["date"], body["amount_ml"], body["source"], body["version"]) == (
            str(user.id),
            "2025-03-10",
            500.0,
            "manual",
            1,
        )
        row = _stored(committed_sessions, uuid.UUID(body["id"]))
        assert (row.user_id, float(row.amount_ml)) == (user.id, 500.0)
        assert me.client.get(response.headers["Location"]).json() == body

    def test_without_a_date_the_record_is_for_the_users_today(self, me):
        assert me.client.post(_URL, json={"amount_ml": 500.0}).json()["date"] == _today().isoformat()

    def test_a_day_that_has_a_record_is_409_and_the_record_is_unchanged(
        self, me, user, make_record, committed_sessions
    ):
        existing = make_record(user, date=_DAY, amount_ml=500.0)

        response = me.client.post(_URL, json={"date": _DAY.isoformat(), "amount_ml": 1200.0})

        assert response.status_code == 409
        assert float(_stored(committed_sessions, existing.id).amount_ml) == 500.0

    def test_a_day_after_the_users_today_is_400(self, me):
        response = me.client.post(_URL, json={"date": (_today() + timedelta(days=1)).isoformat(), "amount_ml": 500.0})

        assert response.status_code == 400

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"date": "2025-03-10"},
            {"amount_ml": -1},
            {"amount_ml": "500.0"},
            {"amount_ml": 500.0, "date": "1899-12-31"},
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
            ("source", "garmin"),
        ],
    )
    def test_a_field_the_server_owns_is_422(self, me, field, value):
        response = me.client.post(_URL, json={"amount_ml": 500.0, field: value})

        assert response.status_code == 422
        assert me.client.get(_URL).json()["total"] == 0


class TestEdit:
    @pytest.fixture
    def record(self, user, make_record):
        return make_record(user, date=_DAY, amount_ml=500.0)

    def _patch(self, client, record_id, body, *, if_match='"1"'):
        headers = {} if if_match is None else {"If-Match": if_match}
        return client.patch(f"{_URL}/{record_id}", json=body, headers=headers)

    def test_the_change_is_applied_and_the_version_and_etag_move_on(self, me, record, committed_sessions):
        response = self._patch(me.client, record.id, {"amount_ml": 900.0})

        assert response.status_code == 200
        assert response.headers["ETag"] == '"2"'
        assert (response.json()["amount_ml"], response.json()["date"], response.json()["version"]) == (
            900.0,
            "2025-03-10",
            2,
        )
        assert me.client.get(f"{_URL}/{record.id}").headers["ETag"] == '"2"'
        row = _stored(committed_sessions, record.id)
        assert (float(row.amount_ml), row.version) == (900.0, 2)

    def test_the_new_etag_lets_the_next_edit_through_and_the_old_one_no_longer(self, me, record):
        assert self._patch(me.client, record.id, {"amount_ml": 900.0}).status_code == 200

        assert self._patch(me.client, record.id, {"amount_ml": 1200.0}, if_match='"2"').status_code == 200
        assert self._patch(me.client, record.id, {"amount_ml": 500.0}, if_match='"2"').status_code == 412

    def test_without_if_match_the_edit_is_428_and_nothing_changes(self, me, record, committed_sessions):
        response = self._patch(me.client, record.id, {"amount_ml": 900.0}, if_match=None)

        assert response.status_code == 428
        assert float(_stored(committed_sessions, record.id).amount_ml) == 500.0

    def test_another_users_record_is_404_and_stays_as_it_was(self, sign_in, other, record, committed_sessions):
        response = self._patch(sign_in(other).client, record.id, {"amount_ml": 900.0})

        assert response.status_code == 404
        row = _stored(committed_sessions, record.id)
        assert (float(row.amount_ml), row.version) == (500.0, 1)

    def test_a_day_after_the_users_today_is_400_and_the_record_keeps_its_day(self, me, record, committed_sessions):
        response = self._patch(me.client, record.id, {"date": (_today() + timedelta(days=1)).isoformat()})

        assert response.status_code == 400
        assert _stored(committed_sessions, record.id).date == _DAY

    def test_moving_to_a_day_that_has_a_record_is_409(self, me, user, record, make_record):
        make_record(user, date=date(2025, 3, 11))

        assert self._patch(me.client, record.id, {"date": "2025-03-11"}).status_code == 409

    @pytest.mark.parametrize(
        "body", [{"amount_ml": None}, {"date": None}, {"amount_ml": -1}, {"id": _ANY_ID}, {"source": "garmin"}]
    )
    def test_a_body_the_schema_refuses_is_422_and_nothing_changes(self, me, record, committed_sessions, body):
        assert self._patch(me.client, record.id, body).status_code == 422
        assert _stored(committed_sessions, record.id).version == 1


class TestDelete:
    @pytest.fixture
    def record(self, user, make_record):
        return make_record(user, date=_DAY)

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
