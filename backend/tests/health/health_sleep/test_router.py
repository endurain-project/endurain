"""The sleep routes, through the production application: real authentication, scopes, handlers and database."""

import uuid
from datetime import date, timedelta

import pytest

import core.config as core_config
import core.timezone as core_timezone
import modules.health.health_sleep.models as health_sleep_models
from tests._factories.health import make_health_sleep
from tests._factories.users import make_user

_URL = f"{core_config.ROOT_PATH}/health/sleep"
_DAY = date(2025, 3, 10)


def _today() -> date:
    return core_timezone.today_in(core_timezone.or_default(None))


def _stored(committed_sessions, record_id):
    """Read a record back in a new session, detached, or ``None`` when it is gone."""
    with committed_sessions() as db:
        row = db.get(health_sleep_models.HealthSleep, record_id)
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
    """Return a function that commits a sleep record for a user and returns it."""

    def make(owner, **overrides):
        with committed_sessions() as db:
            record = make_health_sleep(db, owner.id, **overrides)
            db.commit()
        return record

    return make


class TestList:
    def test_the_users_nights_come_newest_first_in_a_page_envelope_without_their_stages(self, me, user, make_record):
        old = make_record(user, date=date(2025, 3, 1), total_sleep_seconds=20000)
        new = make_record(user, date=date(2025, 3, 9), total_sleep_seconds=30000)

        body = me.client.get(_URL).json()

        assert [item["id"] for item in body["items"]] == [str(new.id), str(old.id)]
        assert (body["total"], body["page"], body["num_records"], body["next"]) == (2, 1, 25, None)
        assert body["items"][0]["has_sleep_stages"] is False
        assert "sleep_stages" not in body["items"][0]

    def test_another_users_nights_are_not_listed(self, me, other, make_record):
        make_record(other)

        body = me.client.get(_URL).json()

        assert (body["items"], body["total"]) == ([], 0)

    def test_a_page_holds_its_slice_and_names_the_next_one(self, me, user, make_record):
        for day in range(1, 6):
            make_record(user, date=date(2025, 3, day))

        first = me.client.get(_URL, params={"page_number": 1, "num_records": 2}).json()

        assert ([i["date"] for i in first["items"]], first["total"], first["next"]) == (
            ["2025-03-05", "2025-03-04"],
            5,
            2,
        )

    def test_the_resting_heart_rate_filter_keeps_the_total_in_step(self, me, user, make_record):
        make_record(user, date=date(2025, 3, 1), resting_heart_rate=50)
        make_record(user, date=date(2025, 3, 2))

        body = me.client.get(_URL, params={"has_resting_heart_rate": "true"}).json()

        assert ([i["date"] for i in body["items"]], body["total"]) == (["2025-03-01"], 1)

    def test_an_interval_looks_back_from_the_users_today(self, me, user, make_record):
        make_record(user, date=_today())
        make_record(user, date=_today() - timedelta(days=40))

        body = me.client.get(_URL, params={"interval": "last_7_days"}).json()

        assert body["total"] == 1

    def test_a_reversed_date_range_is_422(self, me):
        response = me.client.get(_URL, params={"start_date": "2025-03-05", "end_date": "2025-03-01"})

        assert response.status_code == 422


class TestChart:
    def test_the_totals_and_the_resting_heart_rates_are_charted_by_day(self, me, user, make_record):
        make_record(user, date=_today(), total_sleep_seconds=30000, resting_heart_rate=48)
        make_record(user, date=_today() - timedelta(days=1), total_sleep_seconds=20000)

        totals = me.client.get(f"{_URL}/chart", params={"interval": "last_7_days"}).json()
        rate = me.client.get(f"{_URL}/chart/resting-heart-rate", params={"interval": "last_7_days"}).json()

        assert totals["bucket"] == "day"
        assert [(p["date"], p["value"]) for p in totals["points"]] == [
            ((_today() - timedelta(days=1)).isoformat(), 20000.0),
            (_today().isoformat(), 30000.0),
        ]
        assert [(p["date"], p["value"]) for p in rate["points"]] == [(_today().isoformat(), 48.0)]

    def test_another_users_nights_are_not_charted(self, me, other, make_record):
        make_record(other, date=_today())

        assert me.client.get(f"{_URL}/chart").json()["points"] == []


class TestRead:
    def test_the_record_comes_with_its_etag(self, me, user, make_record):
        record = make_record(user, date=_DAY, total_sleep_seconds=27000)

        response = me.client.get(f"{_URL}/{record.id}")

        assert (response.status_code, response.headers["ETag"]) == (200, '"1"')
        assert (response.json()["id"], response.json()["total_sleep_seconds"]) == (str(record.id), 27000)

    def test_another_users_record_is_404(self, me, other, make_record):
        theirs = make_record(other)

        assert me.client.get(f"{_URL}/{theirs.id}").status_code == 404

    def test_an_id_that_is_not_a_uuid_is_422(self, me):
        assert me.client.get(f"{_URL}/not-a-uuid").status_code == 422


class TestCreate:
    def test_the_night_is_stored_scored_and_answered_with_its_location_and_version(self, me, user, committed_sessions):
        response = me.client.post(_URL, json={"date": "2025-03-10", "total_sleep_seconds": 28800, "awake_count": 0})

        assert response.status_code == 201
        body = response.json()
        assert response.headers["Location"] == f"{_URL}/{body['id']}"
        assert response.headers["ETag"] == '"1"'
        assert (body["user_id"], body["date"], body["source"], body["version"]) == (
            str(user.id),
            "2025-03-10",
            "manual",
            1,
        )
        row = _stored(committed_sessions, uuid.UUID(body["id"]))
        assert (row.user_id, row.total_sleep_seconds) == (user.id, 28800)
        assert me.client.get(response.headers["Location"]).json() == body

    def test_without_a_date_the_night_is_for_the_users_today(self, me):
        assert me.client.post(_URL, json={"total_sleep_seconds": 28800}).json()["date"] == _today().isoformat()

    def test_a_day_that_has_a_record_is_409_and_the_record_is_unchanged(
        self, me, user, make_record, committed_sessions
    ):
        existing = make_record(user, date=_DAY, total_sleep_seconds=20000)

        response = me.client.post(_URL, json={"date": _DAY.isoformat(), "total_sleep_seconds": 30000})

        assert response.status_code == 409
        assert _stored(committed_sessions, existing.id).total_sleep_seconds == 20000

    def test_a_day_after_the_users_today_is_400(self, me):
        response = me.client.post(_URL, json={"date": (_today() + timedelta(days=1)).isoformat()})

        assert response.status_code == 400

    def test_stages_that_contradict_the_total_are_400_and_nothing_is_stored(self, me):
        response = me.client.post(
            _URL, json={"date": "2025-03-10", "total_sleep_seconds": 3600, "deep_sleep_seconds": 7200}
        )

        assert response.status_code == 400
        assert me.client.get(_URL).json()["total"] == 0

    @pytest.mark.parametrize(
        "body",
        [
            {"total_sleep_seconds": 3_000_000_000},
            {"awake_count": 3_000_000_000},
            {"avg_respiration": 3_000_000_000},
            {"avg_skin_temp_deviation": 1e9},
            {"sleep_start_time_gmt": "2024-01-15T22:00:00Z", "sleep_end_time_gmt": "2024-01-15T06:00:00"},
            {"total_sleep_seconds": "8h"},
            {"source": "garmin"},
            {"id": "6f1c2a4e-3b7d-4c58-9a10-5d2e8b7c9f01"},
            {"version": 5},
        ],
    )
    def test_a_body_the_schema_refuses_is_422_and_nothing_is_stored(self, me, body):
        assert me.client.post(_URL, json={"date": "2025-03-10", **body}).status_code == 422
        assert me.client.get(_URL).json()["total"] == 0


class TestScoresAreTheServers:
    def test_a_score_sent_on_create_or_edit_is_replaced_by_the_computed_one(self, me):
        night = {"total_sleep_seconds": 28800, "deep_sleep_seconds": 5184, "light_sleep_seconds": 14400}
        created = me.client.post(_URL, json={"date": "2025-03-10", **night, "sleep_score_overall": 1}).json()

        edited = me.client.patch(
            f"{_URL}/{created['id']}", json={"awake_count": 1, "sleep_score_overall": 1}, headers={"If-Match": '"1"'}
        ).json()

        assert created["sleep_score_overall"] != 1
        assert edited["sleep_score_overall"] != 1


class TestEdit:
    @pytest.fixture
    def record(self, user, make_record):
        return make_record(user, date=_DAY, total_sleep_seconds=25200, resting_heart_rate=50)

    def _patch(self, client, record_id, body, *, if_match='"1"'):
        return client.patch(f"{_URL}/{record_id}", json=body, headers={"If-Match": if_match})

    def test_the_change_is_applied_and_the_version_and_etag_move_on(self, me, record, committed_sessions):
        response = self._patch(me.client, record.id, {"resting_heart_rate": 47})

        assert (response.status_code, response.headers["ETag"]) == (200, '"2"')
        assert (response.json()["resting_heart_rate"], response.json()["total_sleep_seconds"]) == (47, 25200)
        row = _stored(committed_sessions, record.id)
        assert (row.resting_heart_rate, row.version) == (47, 2)

    def test_a_stale_version_is_412_and_nothing_changes(self, me, record, committed_sessions):
        assert self._patch(me.client, record.id, {"resting_heart_rate": 40}, if_match='"7"').status_code == 412
        assert _stored(committed_sessions, record.id).resting_heart_rate == 50

    def test_another_users_record_is_404_and_stays_as_it_was(self, sign_in, other, record, committed_sessions):
        response = self._patch(sign_in(other).client, record.id, {"resting_heart_rate": 40})

        assert response.status_code == 404
        assert _stored(committed_sessions, record.id).version == 1

    def test_a_total_beyond_the_stored_stages_is_400(self, me, user, make_record):
        record = make_record(user, date=date(2025, 3, 11), total_sleep_seconds=28800, deep_sleep_seconds=20000)

        assert self._patch(me.client, record.id, {"total_sleep_seconds": 100}).status_code == 400

    def test_a_day_after_the_users_today_is_400_and_the_record_keeps_its_day(self, me, record, committed_sessions):
        response = self._patch(me.client, record.id, {"date": (_today() + timedelta(days=1)).isoformat()})

        assert response.status_code == 400
        assert _stored(committed_sessions, record.id).date == _DAY

    def test_moving_to_a_day_that_has_a_record_is_409(self, me, user, record, make_record):
        make_record(user, date=date(2025, 3, 11))

        assert self._patch(me.client, record.id, {"date": "2025-03-11"}).status_code == 409

    @pytest.mark.parametrize("body", [{"date": None}, {"total_sleep_seconds": -1}, {"id": "x"}])
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

    def test_a_stale_version_is_412_and_the_record_stays(self, me, record, committed_sessions):
        assert me.client.delete(f"{_URL}/{record.id}", headers={"If-Match": '"9"'}).status_code == 412
        assert _stored(committed_sessions, record.id) is not None

    def test_another_users_record_is_404_and_stays(self, sign_in, other, record, committed_sessions):
        response = sign_in(other).client.delete(f"{_URL}/{record.id}", headers={"If-Match": '"1"'})

        assert response.status_code == 404
        assert _stored(committed_sessions, record.id) is not None
