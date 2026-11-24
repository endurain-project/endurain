"""The notification routes, through the production application: real authentication, handlers and database."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

import core.config as core_config
import core.pagination as core_pagination
import modules.notifications.constants as notifications_constants
import modules.notifications.models as notifications_models
from tests._factories.notifications import make_notification_of
from tests._factories.users import make_user

_URL = f"{core_config.ROOT_PATH}/notifications"
_NEW_ACTIVITY = notifications_constants.NotificationType.NEW_ACTIVITY
_T0 = datetime(2024, 1, 1, 10, 30, tzinfo=UTC)


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
def make_record(committed_sessions):
    """Return a function that commits a new-activity notification for a user and returns it."""

    def make(owner, **overrides):
        with committed_sessions() as db:
            record = make_notification_of(db, owner.id, _NEW_ACTIVITY, {"activity_id": str(uuid.uuid4())}, **overrides)
            db.commit()
        return record

    return make


def _read_flags(committed_sessions) -> dict[uuid.UUID, bool]:
    """Read every stored notification's read flag back in a new session."""
    with committed_sessions() as db:
        rows = db.execute(select(notifications_models.Notification.id, notifications_models.Notification.read))
        return {row.id: row.read for row in rows}


class TestUnreadCount:
    def test_it_counts_the_callers_unread_notifications_only(self, me, user, other, make_record):
        make_record(user)
        make_record(user)
        make_record(user, read=True)
        make_record(other)

        response = me.client.get(f"{_URL}/unread-count")

        assert response.status_code == 200
        assert response.json() == {"count": 2}

    def test_a_caller_without_notifications_has_a_zero_count(self, me):
        assert me.client.get(f"{_URL}/unread-count").json() == {"count": 0}

    def test_the_old_number_route_is_gone(self, me):
        assert me.client.get(f"{_URL}/number").status_code == 422


class TestRead:
    def test_the_notification_comes_with_its_options_and_a_utc_timestamp(self, me, user, make_record):
        record = make_record(user, created_at=_T0)

        response = me.client.get(f"{_URL}/{record.id}")

        assert response.status_code == 200
        assert response.json() == {
            "id": str(record.id),
            "user_id": str(user.id),
            "type": "new_activity",
            "options": {"activity_id": str(record.options.activity_id)},
            "read": False,
            "created_at": "2024-01-01T10:30:00Z",
        }

    def test_a_missing_notification_is_404(self, me):
        assert me.client.get(f"{_URL}/{uuid.uuid4()}").status_code == 404

    def test_an_id_that_is_not_a_uuid_is_422(self, me):
        assert me.client.get(f"{_URL}/not-a-uuid").status_code == 422


class TestList:
    def test_the_slice_is_newest_first_and_holds_only_the_callers_rows(self, me, user, other, make_record):
        old = make_record(user, created_at=_T0)
        new = make_record(user, created_at=_T0 + timedelta(days=1))
        make_record(other)

        response = me.client.get(_URL)

        assert response.status_code == 200
        body = response.json()
        assert [item["id"] for item in body["items"]] == [str(new.id), str(old.id)]
        assert (body["num_records"], body["next_cursor"]) == (core_pagination.DEFAULT_NUM_RECORDS, None)
        assert body["items"][0]["created_at"] == "2024-01-02T10:30:00Z"

    def test_the_next_cursor_resumes_the_walk_until_it_is_null(self, me, user, make_record):
        records = [make_record(user, created_at=_T0 + timedelta(days=d)) for d in range(5)]
        newest_first = [str(r.id) for r in reversed(records)]

        first = me.client.get(_URL, params={"num_records": 2}).json()
        second = me.client.get(_URL, params={"num_records": 2, "cursor": first["next_cursor"]}).json()
        third = me.client.get(_URL, params={"num_records": 2, "cursor": second["next_cursor"]}).json()

        assert [i["id"] for i in first["items"]] == newest_first[:2]
        assert [i["id"] for i in second["items"]] == newest_first[2:4]
        assert [i["id"] for i in third["items"]] == newest_first[4:]
        assert third["next_cursor"] is None

    def test_unread_only_leaves_out_the_read_notifications(self, me, user, make_record):
        unread = make_record(user, created_at=_T0)
        make_record(user, read=True, created_at=_T0 + timedelta(days=1))

        body = me.client.get(_URL, params={"unread_only": "true"}).json()

        assert [i["id"] for i in body["items"]] == [str(unread.id)]

    def test_a_cursor_the_server_did_not_issue_is_400(self, me):
        assert me.client.get(_URL, params={"cursor": "garbage"}).status_code == 400

    @pytest.mark.parametrize("num_records", [0, core_pagination.MAX_NUM_RECORDS + 1])
    def test_a_page_size_out_of_range_is_422(self, me, num_records):
        assert me.client.get(_URL, params={"num_records": num_records}).status_code == 422


class TestMarkAsRead:
    def test_the_notification_is_marked_read(self, me, user, make_record, committed_sessions):
        record = make_record(user)

        response = me.client.post(f"{_URL}/{record.id}/read")

        assert response.status_code == 204
        assert _read_flags(committed_sessions) == {record.id: True}

    def test_another_users_or_a_missing_notification_is_404_and_stays_unread(
        self, me, other, make_record, committed_sessions
    ):
        theirs = make_record(other)

        assert me.client.post(f"{_URL}/{theirs.id}/read").status_code == 404
        assert me.client.post(f"{_URL}/{uuid.uuid4()}/read").status_code == 404
        assert _read_flags(committed_sessions) == {theirs.id: False}

    def test_the_ids_in_the_body_are_marked_and_the_ones_that_are_not_the_callers_are_skipped(
        self, me, user, other, make_record, committed_sessions
    ):
        mine = [make_record(user) for _ in range(3)]
        theirs = make_record(other)

        response = me.client.post(f"{_URL}/read", json={"ids": [str(mine[0].id), str(theirs.id), str(uuid.uuid4())]})

        assert response.status_code == 204
        assert _read_flags(committed_sessions) == {
            mine[0].id: True,
            mine[1].id: False,
            mine[2].id: False,
            theirs.id: False,
        }

    def test_without_a_body_every_unread_notification_of_the_caller_is_marked(
        self, me, user, other, make_record, committed_sessions
    ):
        mine = [make_record(user) for _ in range(2)]
        theirs = make_record(other)

        response = me.client.post(f"{_URL}/read")

        assert response.status_code == 204
        assert _read_flags(committed_sessions) == {mine[0].id: True, mine[1].id: True, theirs.id: False}

    @pytest.mark.parametrize(
        "body",
        [
            {"ids": []},
            {"ids": [0]},
            {"ids": ["not-a-uuid"]},
            {"ids": [str(uuid.UUID(int=1))], "all": True},
            {},
        ],
    )
    def test_a_body_the_route_does_not_accept_is_422_and_marks_nothing(
        self, me, user, make_record, committed_sessions, body
    ):
        record = make_record(user)

        assert me.client.post(f"{_URL}/read", json=body).status_code == 422
        assert _read_flags(committed_sessions) == {record.id: False}

    def test_more_ids_than_one_request_may_mark_is_422(self, me):
        ids = [str(uuid.uuid4()) for _ in range(101)]

        assert me.client.post(f"{_URL}/read", json={"ids": ids}).status_code == 422


class TestDelete:
    def test_the_callers_notification_is_deleted(self, me, user, make_record, committed_sessions):
        record = make_record(user)

        response = me.client.delete(f"{_URL}/{record.id}")

        assert response.status_code == 204
        assert _read_flags(committed_sessions) == {}

    def test_another_users_or_a_missing_notification_is_404_and_kept(self, me, other, make_record, committed_sessions):
        theirs = make_record(other)

        assert me.client.delete(f"{_URL}/{theirs.id}").status_code == 404
        assert me.client.delete(f"{_URL}/{uuid.uuid4()}").status_code == 404
        assert _read_flags(committed_sessions) == {theirs.id: False}
