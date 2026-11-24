"""The profile overview route: a user's public profile with what the viewer may see of their activity and network."""

import uuid
from datetime import UTC, datetime

import jasil.runtime as jasil_runtime
import pytest

import core.config as core_config
import modules.activities.activity.constants as activity_constants
from tests._factories.activities import make_activity
from tests._factories.followers import make_follow
from tests._factories.users import make_user

_API = core_config.ROOT_PATH
# Wednesday noon UTC; the week runs Monday 10th to Sunday 16th.
_NOW = datetime(2025, 3, 12, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clock():
    jasil_runtime.get_active_platform().clock.moment = _NOW


@pytest.fixture
def owner(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db, name="Ada Runner", timezone="UTC")
        db.commit()
    return created


@pytest.fixture
def viewer(committed_sessions, sign_in):
    with committed_sessions() as db:
        created = make_user(db, timezone="UTC")
        db.commit()
    return sign_in(created)


def _overview(client, user_id, **params):
    return client.get(f"{_API}/users/{user_id}/overview", params=params)


def _activity(committed_sessions, owner, day, visibility, **fields):
    with committed_sessions() as db:
        make_activity(db, owner.id, visibility=visibility, start_time=datetime(2025, 3, day, 8, tzinfo=UTC), **fields)
        db.commit()


class TestPublicProfile:
    def test_the_profile_carries_the_public_projection_only(self, viewer, owner):
        response = _overview(viewer.client, owner.id)

        assert response.status_code == 200
        user = response.json()["user"]
        assert (user["id"], user["name"], user["username"]) == (str(owner.id), "Ada Runner", owner.username)
        assert "email" not in user

    def test_a_missing_user_is_not_found(self, viewer):
        assert _overview(viewer.client, uuid.uuid4()).status_code == 404

    def test_an_inactive_user_is_not_found(self, committed_sessions, viewer):
        with committed_sessions() as db:
            gone = make_user(db, active=False)
            db.commit()

        assert _overview(viewer.client, gone.id).status_code == 404


class TestActivitySummary:
    def test_a_stranger_sees_only_the_public_activities_of_the_week_and_month(self, committed_sessions, viewer, owner):
        public, private = activity_constants.ActivityVisibility.PUBLIC, activity_constants.ActivityVisibility.PRIVATE
        _activity(committed_sessions, owner, 11, public, distance=10000)
        _activity(committed_sessions, owner, 12, private, distance=99999)
        _activity(committed_sessions, owner, 3, public, distance=5000)

        body = _overview(viewer.client, owner.id).json()

        assert body["week_stats"]["run"]["distance"] == 10000
        assert body["month_stats"]["run"]["distance"] == 15000
        assert body["month_activity_count"] == 2

    def test_the_owner_sees_every_visibility(self, committed_sessions, sign_in, owner):
        _activity(committed_sessions, owner, 11, activity_constants.ActivityVisibility.PRIVATE, distance=7000)

        body = _overview(sign_in(owner).client, owner.id).json()

        assert body["week_stats"]["run"]["distance"] == 7000

    def test_the_date_the_viewer_sends_moves_the_week_and_month(self, committed_sessions, viewer, owner):
        public = activity_constants.ActivityVisibility.PUBLIC
        _activity(committed_sessions, owner, 11, public, distance=10000)

        body = _overview(viewer.client, owner.id, date="2025-02-14").json()

        assert body["week_stats"]["run"]["distance"] == 0
        assert body["month_activity_count"] == 0


class TestNetwork:
    def test_the_counts_are_hidden_from_a_stranger(self, committed_sessions, viewer, owner):
        with committed_sessions() as db:
            make_follow(db, viewer.user.id, owner.id, accepted=False)
            db.commit()

        body = _overview(viewer.client, owner.id).json()

        assert (body["followers_count"], body["following_count"]) == (None, None)

    def test_an_accepted_follower_sees_the_counts(self, committed_sessions, viewer, owner):
        with committed_sessions() as db:
            other = make_user(db)
            make_follow(db, viewer.user.id, owner.id, accepted=True)
            make_follow(db, other.id, owner.id, accepted=True)
            make_follow(db, owner.id, other.id, accepted=True)
            db.commit()

        body = _overview(viewer.client, owner.id).json()

        assert (body["followers_count"], body["following_count"]) == (2, 1)

    def test_the_owner_sees_their_own_counts(self, sign_in, owner):
        body = _overview(sign_in(owner).client, owner.id).json()

        assert (body["followers_count"], body["following_count"]) == (0, 0)
