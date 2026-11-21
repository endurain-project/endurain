"""The fasting routes, through the production application: real authentication, scopes and database."""

import uuid
from datetime import UTC, datetime, timedelta

import jasil.runtime as platform_runtime
import pytest

import core.config as core_config
import modules.health.health_fasting.models as health_fasting_models
from tests._factories.health import make_ended_health_fasting, make_health_fasting
from tests._factories.users import make_user

_URL = f"{core_config.ROOT_PATH}/health/fasting"
_NOW = datetime(2025, 3, 20, 12, 0, tzinfo=UTC)
_T0 = datetime(2025, 3, 10, 8, 0, tzinfo=UTC)
_ANY_ID = "6f1c2a4e-3b7d-4c58-9a10-5d2e8b7c9f01"


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _hours(n: float) -> datetime:
    return _T0 + timedelta(hours=n)


@pytest.fixture(autouse=True)
def now():
    """Stand the platform clock at :data:`_NOW`."""
    platform_runtime.get_active_platform().clock.moment = _NOW


def _stored(committed_sessions, record_id):
    """Read a record back in a new session, detached, or ``None`` when it is gone."""
    with committed_sessions() as db:
        row = db.get(health_fasting_models.HealthFasting, record_id)
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
    """Return a function that commits a fast for a user, ended when an end time is given, and returns it."""

    def make(owner, start=None, end=None, **overrides):
        with committed_sessions() as db:
            if end is None:
                record = make_health_fasting(db, owner.id, **({"fast_start_time": start} if start else {}), **overrides)
            else:
                record = make_ended_health_fasting(db, owner.id, start, end, **overrides)
            db.commit()
        return record

    return make


class TestList:
    def test_the_users_fasts_come_newest_first_in_a_page_envelope(self, me, user, make_record):
        old = make_record(user, _hours(0), _hours(10), notes="old")
        new = make_record(user, _hours(48), _hours(60))

        response = me.client.get(_URL)

        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body["items"]] == [str(new.id), str(old.id)]
        assert (body["total"], body["page"], body["num_records"], body["next"]) == (2, 1, 25, None)
        assert body["items"][1] == {
            "id": str(old.id),
            "user_id": str(user.id),
            "fast_start_time": _iso(_hours(0)),
            "fast_end_time": _iso(_hours(10)),
            "target_duration_seconds": None,
            "actual_duration_seconds": 36000,
            "fasting_type": None,
            "status": "completed",
            "notes": "old",
            "source": "manual",
            "version": 1,
            "updated_at": body["items"][1]["updated_at"],
        }

    def test_another_users_fasts_are_not_listed(self, me, other, make_record):
        make_record(other)

        assert me.client.get(_URL).json()["total"] == 0

    def test_a_page_holds_its_slice_the_range_is_inclusive_and_an_interval_looks_back_from_the_users_today(
        self, me, user, make_record
    ):
        for day in range(1, 6):
            start = datetime(2025, 3, day * 3, 8, 0, tzinfo=UTC)
            make_record(user, start, start + timedelta(hours=2))

        page = me.client.get(_URL, params={"page_number": 2, "num_records": 2}).json()
        ranged = me.client.get(_URL, params={"start_date": "2025-03-06", "end_date": "2025-03-12"}).json()
        windowed = me.client.get(_URL, params={"interval": "last_7_days"}).json()

        assert ([i["fast_start_time"][:10] for i in page["items"]], page["total"], page["next"]) == (
            ["2025-03-09", "2025-03-06"],
            5,
            3,
        )
        assert ranged["total"] == 3
        assert windowed["total"] == 1  # only the fast of the 15th starts within seven days of the 20th

    @pytest.mark.parametrize("params", [{"page_number": 0}, {"num_records": 201}, {"interval": "last_century"}])
    def test_a_query_the_route_does_not_accept_is_422(self, me, params):
        assert me.client.get(_URL, params=params).status_code == 422


class TestRead:
    def test_the_fast_comes_with_its_version_as_the_etag(self, me, user, make_record):
        record = make_record(user, _hours(0), _hours(10))

        response = me.client.get(f"{_URL}/{record.id}")

        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        assert response.json()["id"] == str(record.id)

    def test_a_fast_the_user_does_not_have_is_404(self, me):
        assert me.client.get(f"{_URL}/{uuid.uuid4()}").status_code == 404

    def test_another_users_fast_is_404(self, me, other, make_record):
        assert me.client.get(f"{_URL}/{make_record(other).id}").status_code == 404


class TestActive:
    def test_the_running_fast_is_answered_with_its_etag(self, me, user, make_record):
        make_record(user, _hours(0), _hours(10))
        running = make_record(user, _hours(48), status="in_progress")

        response = me.client.get(f"{_URL}/active")

        assert response.status_code == 200
        assert (response.json()["id"], response.headers["ETag"]) == (str(running.id), '"1"')

    def test_without_a_running_fast_the_answer_is_null_and_there_is_no_etag(self, me, other, make_record):
        make_record(other, status="in_progress")

        response = me.client.get(f"{_URL}/active")

        assert (response.status_code, response.json(), "ETag" in response.headers) == (200, None, False)


class TestStats:
    def test_the_statistics_cover_the_users_completed_fasts_only(self, me, user, other, make_record):
        for days_ago in (0, 1):
            start = datetime(2025, 3, 20, 6, 0, tzinfo=UTC) - timedelta(days=days_ago)
            make_record(user, start, start + timedelta(hours=10))
        make_record(user, _hours(0), _hours(5), status="broken")
        make_record(other, _hours(0), _hours(50))

        body = me.client.get(f"{_URL}/stats").json()

        assert body == {
            "total_fasts": 2,
            "current_streak": 2,
            "longest_streak": 2,
            "avg_duration_seconds": 36000,
            "total_fasting_seconds": 72000,
            "completion_rate": 66.7,
        }


class TestCreate:
    def test_the_fast_is_stored_and_answered_with_its_location_version_and_derived_duration(
        self, me, user, committed_sessions
    ):
        response = me.client.post(
            _URL,
            json={
                "fast_start_time": "2025-03-10T08:00:00+00:00",
                "fast_end_time": "2025-03-10T18:00:00+00:00",
                "status": "completed",
                "fasting_type": "16:8",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert response.headers["Location"] == f"{_URL}/{body['id']}"
        assert response.headers["ETag"] == '"1"'
        assert (body["user_id"], body["actual_duration_seconds"], body["source"], body["fasting_type"]) == (
            str(user.id),
            36000,
            "manual",
            "16:8",
        )
        assert _stored(committed_sessions, uuid.UUID(body["id"])).actual_duration_seconds == 36000

    def test_a_fast_without_a_status_starts_running(self, me):
        body = me.client.post(_URL, json={"fast_start_time": "2025-03-10T08:00:00Z"}).json()

        assert (body["status"], body["fast_end_time"], body["actual_duration_seconds"]) == ("in_progress", None, None)

    def test_a_second_running_fast_is_409_and_the_first_stays(self, me, user, make_record):
        running = make_record(user, _hours(0), status="in_progress")

        response = me.client.post(_URL, json={"fast_start_time": "2025-03-12T08:00:00Z"})

        assert response.status_code == 409
        assert me.client.get(f"{_URL}/active").json()["id"] == str(running.id)

    def test_a_fast_that_overlaps_another_is_409(self, me, user, make_record):
        make_record(user, _hours(0), _hours(10))
        body = {"fast_start_time": _iso(_hours(5)), "fast_end_time": _iso(_hours(15)), "status": "completed"}

        response = me.client.post(_URL, json=body)

        assert response.status_code == 409
        assert me.client.get(_URL).json()["total"] == 1

    @pytest.mark.parametrize(
        "body",
        [
            {"fast_start_time": "2025-03-10T08:00:00Z", "fast_end_time": "2025-03-10T06:00:00Z", "status": "completed"},
            {"fast_start_time": "2025-03-10T08:00:00Z", "status": "completed"},
            {
                "fast_start_time": "2025-03-10T08:00:00Z",
                "fast_end_time": "2025-03-10T09:00:00Z",
                "status": "in_progress",
            },
            {"fast_start_time": "2025-03-25T08:00:00Z"},
        ],
        ids=["end-before-start", "completed-without-end", "in-progress-with-end", "in-the-future"],
    )
    def test_times_that_cannot_describe_one_fast_are_400_and_nothing_is_stored(self, me, body):
        assert me.client.post(_URL, json=body).status_code == 400
        assert me.client.get(_URL).json()["total"] == 0

    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"fast_start_time": "2025-03-10T08:00:00"},
            {"fast_start_time": "2025-03-10T08:00:00Z", "fasting_type": "17:7"},
            {"fast_start_time": "2025-03-10T08:00:00Z", "status": "paused"},
            {"fast_start_time": "2025-03-10T08:00:00Z", "target_duration_seconds": "10"},
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
            ("source", "garmin"),
            ("actual_duration_seconds", 5),
        ],
    )
    def test_a_field_the_server_owns_is_422(self, me, field, value):
        response = me.client.post(_URL, json={"fast_start_time": "2025-03-10T08:00:00Z", field: value})

        assert response.status_code == 422
        assert me.client.get(_URL).json()["total"] == 0


class TestEdit:
    @pytest.fixture
    def record(self, user, make_record):
        return make_record(user, _hours(0), _hours(10), notes="before")

    def _patch(self, client, record_id, body, *, if_match='"1"'):
        headers = {} if if_match is None else {"If-Match": if_match}
        return client.patch(f"{_URL}/{record_id}", json=body, headers=headers)

    def test_the_change_is_applied_the_duration_follows_and_the_etag_moves_on(self, me, record, committed_sessions):
        response = self._patch(me.client, record.id, {"fast_end_time": _iso(_hours(12)), "notes": "after"})

        assert response.status_code == 200
        assert response.headers["ETag"] == '"2"'
        body = response.json()
        assert (body["notes"], body["actual_duration_seconds"], body["version"]) == ("after", 12 * 3600, 2)
        row = _stored(committed_sessions, record.id)
        assert (row.notes, row.actual_duration_seconds, row.version) == ("after", 12 * 3600, 2)

    def test_the_old_etag_no_longer_lets_an_edit_through(self, me, record):
        assert self._patch(me.client, record.id, {"notes": "a"}).status_code == 200

        assert self._patch(me.client, record.id, {"notes": "b"}).status_code == 412

    def test_without_if_match_the_edit_is_428_and_nothing_changes(self, me, record, committed_sessions):
        assert self._patch(me.client, record.id, {"notes": "x"}, if_match=None).status_code == 428
        assert _stored(committed_sessions, record.id).notes == "before"

    def test_another_users_fast_is_404_and_stays_as_it_was(self, sign_in, other, record, committed_sessions):
        response = self._patch(sign_in(other).client, record.id, {"notes": "mine"})

        assert response.status_code == 404
        assert _stored(committed_sessions, record.id).notes == "before"

    def test_an_end_before_the_start_is_400_and_the_fast_keeps_its_end(self, me, record, committed_sessions):
        response = self._patch(me.client, record.id, {"fast_end_time": _iso(_hours(-3))})

        assert response.status_code == 400
        assert _stored(committed_sessions, record.id).fast_end_time == _hours(10)

    def test_moving_a_fast_into_another_is_409(self, me, user, record, make_record):
        later = make_record(user, _hours(20), _hours(30))

        assert self._patch(me.client, later.id, {"fast_start_time": _iso(_hours(5))}).status_code == 409

    @pytest.mark.parametrize(
        "body", [{"fast_start_time": None}, {"status": "paused"}, {"id": _ANY_ID}, {"actual_duration_seconds": 1}]
    )
    def test_a_body_the_schema_refuses_is_422_and_nothing_changes(self, me, record, committed_sessions, body):
        assert self._patch(me.client, record.id, body).status_code == 422
        assert _stored(committed_sessions, record.id).version == 1


class TestComplete:
    @pytest.fixture
    def running(self, user, make_record):
        return make_record(user, _hours(0), status="in_progress", notes="kept")

    def _complete(self, client, record_id, body, *, if_match='"1"'):
        headers = {} if if_match is None else {"If-Match": if_match}
        return client.post(f"{_URL}/{record_id}/complete", json=body, headers=headers)

    def test_the_fast_ends_with_the_derived_duration_and_the_new_etag(self, me, running, committed_sessions):
        response = self._complete(me.client, running.id, {"fast_end_time": _iso(_hours(16))})

        assert response.status_code == 200
        assert response.headers["ETag"] == '"2"'
        body = response.json()
        assert (body["status"], body["actual_duration_seconds"], body["notes"]) == ("completed", 16 * 3600, "kept")
        assert me.client.get(f"{_URL}/active").json() is None
        assert _stored(committed_sessions, running.id).fast_end_time == _hours(16)

    def test_the_final_status_and_notes_sent_are_stored(self, me, running):
        body = self._complete(
            me.client, running.id, {"fast_end_time": _iso(_hours(5)), "status": "broken", "notes": "gave in"}
        ).json()

        assert (body["status"], body["notes"]) == ("broken", "gave in")

    def test_a_fast_that_has_ended_is_409(self, me, user, make_record):
        ended = make_record(user, _hours(0), _hours(5))

        assert self._complete(me.client, ended.id, {"fast_end_time": _iso(_hours(6))}).status_code == 409

    def test_an_end_before_the_start_is_400_and_the_fast_keeps_running(self, me, running, committed_sessions):
        response = self._complete(me.client, running.id, {"fast_end_time": _iso(_hours(-2))})

        assert response.status_code == 400
        assert _stored(committed_sessions, running.id).status == "in_progress"

    def test_a_final_status_of_in_progress_is_422(self, me, running):
        assert (
            self._complete(
                me.client, running.id, {"fast_end_time": _iso(_hours(5)), "status": "in_progress"}
            ).status_code
            == 422
        )

    def test_a_stale_version_is_412_and_without_if_match_428(self, me, running, committed_sessions):
        stale = self._complete(me.client, running.id, {"fast_end_time": _iso(_hours(5))}, if_match='"9"')
        missing = self._complete(me.client, running.id, {"fast_end_time": _iso(_hours(5))}, if_match=None)

        assert (stale.status_code, missing.status_code) == (412, 428)
        assert _stored(committed_sessions, running.id).status == "in_progress"

    def test_another_users_fast_is_404(self, sign_in, other, running):
        assert self._complete(sign_in(other).client, running.id, {"fast_end_time": _iso(_hours(5))}).status_code == 404


class TestDelete:
    @pytest.fixture
    def record(self, user, make_record):
        return make_record(user, _hours(0), _hours(10))

    def test_the_fast_is_deleted_with_no_body_and_is_gone_afterwards(self, me, record, committed_sessions):
        response = me.client.delete(f"{_URL}/{record.id}", headers={"If-Match": '"1"'})

        assert (response.status_code, response.content) == (204, b"")
        assert _stored(committed_sessions, record.id) is None
        assert me.client.get(f"{_URL}/{record.id}").status_code == 404

    def test_a_stale_version_is_412_and_the_fast_stays(self, me, record, committed_sessions):
        assert me.client.delete(f"{_URL}/{record.id}", headers={"If-Match": '"9"'}).status_code == 412
        assert _stored(committed_sessions, record.id) is not None

    def test_another_users_fast_is_404_and_stays(self, sign_in, other, record, committed_sessions):
        response = sign_in(other).client.delete(f"{_URL}/{record.id}", headers={"If-Match": '"1"'})

        assert response.status_code == 404
        assert _stored(committed_sessions, record.id) is not None
