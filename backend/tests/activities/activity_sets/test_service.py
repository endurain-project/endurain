"""Who reads an activity's workout sets and which fields each viewer gets, on the real database."""

import pytest

import modules.activities.activity.constants as activity_constants
import modules.activities.activity_sets.service as sets_service
from tests._factories.activities import DEFAULT_START, make_activity, make_sets
from tests._factories.followers import make_follow
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user

_VISIBILITY = activity_constants.ActivityVisibility
_SET = {"start_time": DEFAULT_START.isoformat(), "duration": 30.0, "set_type": "active", "repetitions": 10}


@pytest.fixture
def owner(db):
    return make_user(db)


@pytest.fixture
def follower(db, owner):
    user = make_user(db)
    make_follow(db, user.id, owner.id, accepted=True)
    return user


def _shared(db, owner, visibility=_VISIBILITY.FOLLOWERS, **flags):
    activity = make_activity(db, owner.id, visibility=visibility, **flags)
    make_sets(db, activity, [_SET])
    return activity


class TestAuthenticatedRead:
    def test_the_owner_reads_the_sets_whole_whatever_the_flags_say(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PRIVATE, hide_start_time=True, hide_workout_sets_steps=True)

        [workout_set] = sets_service.list_activity_sets(activity.id, owner.id, db).items

        assert (workout_set.start_time, workout_set.repetitions) == (DEFAULT_START, 10)

    def test_hide_start_time_clears_the_start_of_a_set_for_a_follower_and_nothing_else(self, db, owner, follower):
        activity = _shared(db, owner, hide_start_time=True)

        [workout_set] = sets_service.list_activity_sets(activity.id, follower.id, db).items

        assert (workout_set.start_time, workout_set.repetitions, workout_set.duration) == (None, 10, 30.0)

    def test_a_follower_gets_the_set_whole_when_no_flag_is_set(self, db, owner, follower):
        activity = _shared(db, owner)

        [workout_set] = sets_service.list_activity_sets(activity.id, follower.id, db).items

        assert workout_set.start_time == DEFAULT_START

    def test_hide_workout_sets_steps_gives_a_follower_an_empty_page(self, db, owner, follower):
        activity = _shared(db, owner, hide_workout_sets_steps=True)

        page = sets_service.list_activity_sets(activity.id, follower.id, db)

        assert (page.items, page.total) == ([], 0)

    def test_a_stranger_gets_the_page_of_an_activity_that_does_not_exist(self, db, owner):
        activity = _shared(db, owner)

        refused = sets_service.list_activity_sets(activity.id, make_user(db).id, db)

        assert (refused.items, refused.total, refused.next) == ([], 0, None)

    def test_the_sets_a_viewer_sees_with_the_activity_are_the_first_page_masked_for_them(self, db, owner, follower):
        activity = _shared(db, owner, hide_start_time=True)

        assert sets_service.list_for_activity(activity, follower.id, db).items[0].start_time is None
        assert sets_service.list_for_activity(activity, None, db).items[0].start_time is None
        assert sets_service.list_for_activity(activity, owner.id, db).items[0].start_time == DEFAULT_START


class TestPublicRead:
    @pytest.fixture(autouse=True)
    def _links_on(self, db):
        edit_server_settings(db, public_shareable_links=True)

    def test_the_sets_of_a_public_activity_are_served_masked_by_its_flags(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PUBLIC, hide_start_time=True)

        [workout_set] = sets_service.list_public_activity_sets(activity.id, db).items

        assert (workout_set.start_time, workout_set.repetitions) == (None, 10)

    @pytest.mark.parametrize("visibility", [_VISIBILITY.FOLLOWERS, _VISIBILITY.PRIVATE])
    def test_an_activity_that_is_not_public_serves_no_sets(self, db, owner, visibility):
        activity = _shared(db, owner, visibility)

        assert sets_service.list_public_activity_sets(activity.id, db).items == []

    def test_a_hidden_activity_and_a_hidden_collection_serve_no_sets(self, db, owner):
        hidden = _shared(db, owner, _VISIBILITY.PUBLIC, is_hidden=True)
        collapsed = _shared(
            db,
            owner,
            _VISIBILITY.PUBLIC,
            hide_workout_sets_steps=True,
            start_time=DEFAULT_START.replace(day=12),
            end_time=DEFAULT_START.replace(day=12, hour=9),
        )

        assert sets_service.list_public_activity_sets(hidden.id, db).total == 0
        assert sets_service.list_public_activity_sets(collapsed.id, db).total == 0

    def test_turning_public_links_off_serves_no_sets(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PUBLIC)
        edit_server_settings(db, public_shareable_links=False)

        assert sets_service.list_public_activity_sets(activity.id, db).items == []
