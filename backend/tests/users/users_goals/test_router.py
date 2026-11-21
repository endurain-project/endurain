"""The goals routes through the production application: the user's own goals, ETags and their progress."""

import uuid
from datetime import UTC, datetime

import jasil.runtime as jasil_runtime
import pytest

import core.config as core_config
import modules.users.users_goals.crud as crud
from tests._factories.activities import make_activity
from tests._factories.goals import make_goal
from tests._factories.users import make_user

_URL = f"{core_config.ROOT_PATH}/profile/goals"
_BODY = {"interval": "weekly", "activity_type": "run", "goal_type": "distance", "goal_distance": 50000}


@pytest.fixture
def user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db, timezone="UTC", first_day_of_week="monday")
        db.commit()
    return created


@pytest.fixture
def me(sign_in, user):
    return sign_in(user)


@pytest.fixture
def make_owned(committed_sessions, user):
    """Return a function that commits a goal of the signed-in user."""

    def make(**overrides):
        with committed_sessions() as db:
            goal = make_goal(db, user.id, **overrides)
            db.commit()
        return goal

    return make


def _stored(committed_sessions, user_id, goal_id):
    with committed_sessions() as db:
        return crud.get_user_goal(user_id, goal_id, db) if crud.user_goal_exists(user_id, goal_id, db) else None


class TestList:
    def test_the_users_goals_come_in_a_page_and_the_filters_apply(self, me, make_owned):
        weekly = make_owned(interval="weekly")
        make_owned(interval="monthly")

        everything = me.client.get(_URL).json()
        filtered = me.client.get(_URL, params={"interval": "weekly"}).json()

        assert (everything["total"], everything["next"]) == (2, None)
        assert [item["id"] for item in filtered["items"]] == [str(weekly.id)]
        assert filtered["total"] == 1

    def test_another_users_goals_are_not_listed(self, me, committed_sessions):
        with committed_sessions() as db:
            stranger = make_user(db)
            make_goal(db, stranger.id)
            db.commit()

        assert me.client.get(_URL).json()["items"] == []

    def test_an_unknown_filter_value_is_a_validation_error(self, me):
        assert me.client.get(_URL, params={"interval": "hourly"}).status_code == 422

    def test_an_oversized_page_is_refused(self, me):
        assert me.client.get(_URL, params={"num_records": 100000}).status_code == 422


class TestRead:
    def test_a_goal_carries_its_version_as_an_etag(self, me, make_owned):
        goal = make_owned()

        response = me.client.get(f"{_URL}/{goal.id}")

        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        assert response.json()["goal_distance"] == 50000

    def test_a_missing_goal_is_not_found(self, me):
        assert me.client.get(f"{_URL}/{uuid.uuid4()}").status_code == 404

    def test_a_goal_id_that_is_not_a_uuid_is_a_validation_error(self, me):
        assert me.client.get(f"{_URL}/not-a-uuid").status_code == 422


class TestCreate:
    def test_a_goal_is_created_with_its_location_and_etag(self, me, user, committed_sessions):
        response = me.client.post(_URL, json=_BODY)

        assert response.status_code == 201
        goal_id = uuid.UUID(response.json()["id"])
        assert response.headers["Location"].endswith(f"/profile/goals/{goal_id}")
        assert response.headers["ETag"] == '"1"'
        stored = _stored(committed_sessions, user.id, goal_id)
        assert stored is not None
        assert stored.goal_distance == 50000

    def test_a_second_goal_in_the_same_slot_is_a_conflict(self, me, make_owned):
        make_owned()

        response = me.client.post(_URL, json=_BODY)

        assert response.status_code == 409

    @pytest.mark.parametrize(
        "body",
        [
            {"interval": "weekly", "activity_type": "run", "goal_type": "distance"},
            {**_BODY, "user_id": str(uuid.uuid4())},
            {**_BODY, "goal_distance": -1},
        ],
        ids=["missing-target", "owner-field", "negative-target"],
    )
    def test_an_invalid_goal_is_a_validation_error(self, me, body):
        assert me.client.post(_URL, json=body).status_code == 422


class TestReplace:
    def test_the_goal_is_replaced_and_the_new_version_returned(self, me, user, make_owned, committed_sessions):
        goal = make_owned()
        body = {"interval": "weekly", "activity_type": "run", "goal_type": "calories", "goal_calories": 4000}

        response = me.client.put(f"{_URL}/{goal.id}", json=body, headers={"If-Match": '"1"'})

        assert response.status_code == 200
        assert response.headers["ETag"] == '"2"'
        stored = _stored(committed_sessions, user.id, goal.id)
        assert stored is not None
        assert (stored.goal_calories, stored.goal_distance) == (4000, None)

    def test_a_stale_version_is_refused_and_the_goal_is_unchanged(self, me, user, make_owned, committed_sessions):
        goal = make_owned()

        response = me.client.put(f"{_URL}/{goal.id}", json={**_BODY, "goal_distance": 1}, headers={"If-Match": '"9"'})

        assert response.status_code == 412
        stored = _stored(committed_sessions, user.id, goal.id)
        assert stored is not None
        assert (stored.goal_distance, stored.version) == (50000, 1)

    def test_moving_a_goal_into_an_occupied_slot_is_a_conflict(self, me, make_owned):
        make_owned(interval="weekly")
        monthly = make_owned(interval="monthly")

        response = me.client.put(f"{_URL}/{monthly.id}", json=_BODY, headers={"If-Match": '"1"'})

        assert response.status_code == 409

    def test_another_users_goal_is_not_found_and_stays_unchanged(self, me, committed_sessions):
        with committed_sessions() as db:
            stranger = make_user(db)
            theirs = make_goal(db, stranger.id)
            db.commit()

        response = me.client.put(f"{_URL}/{theirs.id}", json={**_BODY, "goal_distance": 1}, headers={"If-Match": '"1"'})

        assert response.status_code == 404
        stored = _stored(committed_sessions, stranger.id, theirs.id)
        assert stored is not None
        assert stored.goal_distance == 50000


class TestDelete:
    def test_the_goal_is_deleted(self, me, user, make_owned, committed_sessions):
        goal = make_owned()

        response = me.client.delete(f"{_URL}/{goal.id}", headers={"If-Match": '"1"'})

        assert response.status_code == 204
        assert _stored(committed_sessions, user.id, goal.id) is None

    def test_a_stale_version_keeps_the_goal(self, me, user, make_owned, committed_sessions):
        goal = make_owned()

        response = me.client.delete(f"{_URL}/{goal.id}", headers={"If-Match": '"3"'})

        assert response.status_code == 412
        assert _stored(committed_sessions, user.id, goal.id) is not None

    def test_a_missing_goal_is_not_found(self, me):
        assert me.client.delete(f"{_URL}/{uuid.uuid4()}", headers={"If-Match": '"1"'}).status_code == 404


class TestResults:
    def test_progress_is_measured_on_the_users_own_day(self, me, user, make_owned, committed_sessions):
        jasil_runtime.get_active_platform().clock.moment = datetime(2025, 3, 12, 12, 0, tzinfo=UTC)
        make_owned()
        with committed_sessions() as db:
            make_activity(db, user.id, start_time=datetime(2025, 3, 11, 8, 0, tzinfo=UTC), distance=20000)
            db.commit()

        response = me.client.get(f"{_URL}/results")

        assert response.status_code == 200
        item = response.json()["items"][0]
        assert (item["start_date"], item["end_date"]) == ("2025-03-10", "2025-03-16")
        assert (item["total_distance"], item["percentage_completed"]) == (20000, 40)

    def test_no_goals_is_an_empty_page(self, me):
        body = me.client.get(f"{_URL}/results").json()

        assert (body["items"], body["total"]) == ([], 0)

    def test_an_oversized_page_is_refused(self, me):
        assert me.client.get(f"{_URL}/results", params={"num_records": 100000}).status_code == 422
