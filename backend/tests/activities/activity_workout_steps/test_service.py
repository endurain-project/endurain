"""Who reads an activity's workout steps, on the real database."""

import pytest

import modules.activities.activity.constants as activity_constants
import modules.activities.activity_workout_steps.service as steps_service
from tests._factories.activities import DEFAULT_START, make_activity, make_workout_steps
from tests._factories.followers import make_follow
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user

_VISIBILITY = activity_constants.ActivityVisibility
_STEP = {"message_index": 0, "duration_type": "time", "duration_value": 300.0, "notes": "easy"}


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
    make_workout_steps(db, activity, [_STEP])
    return activity


class TestAuthenticatedRead:
    def test_the_owner_reads_the_steps_whatever_the_flags_say(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PRIVATE, hide_workout_sets_steps=True)

        page = steps_service.list_activity_workout_steps(activity.id, owner.id, db)

        assert [step.notes for step in page.items] == ["easy"]

    def test_a_follower_reads_the_steps_of_a_followers_only_activity(self, db, owner, follower):
        activity = _shared(db, owner)

        page = steps_service.list_activity_workout_steps(activity.id, follower.id, db)

        assert (page.total, page.items[0].duration_value) == (1, 300.0)

    def test_hide_workout_sets_steps_gives_a_follower_an_empty_page(self, db, owner, follower):
        activity = _shared(db, owner, hide_workout_sets_steps=True)

        page = steps_service.list_activity_workout_steps(activity.id, follower.id, db)

        assert (page.items, page.total) == ([], 0)

    def test_the_other_hide_flags_do_not_withhold_the_steps(self, db, owner, follower):
        activity = _shared(db, owner, hide_laps=True, hide_hr=True, hide_start_time=True)

        assert steps_service.list_activity_workout_steps(activity.id, follower.id, db).total == 1

    def test_a_stranger_gets_the_page_of_an_activity_that_does_not_exist(self, db, owner):
        activity = _shared(db, owner)

        refused = steps_service.list_activity_workout_steps(activity.id, make_user(db).id, db)

        assert (refused.items, refused.total, refused.next) == ([], 0, None)

    def test_the_steps_a_viewer_sees_with_the_activity_are_the_first_page_unless_hidden(self, db, owner, follower):
        activity = _shared(db, owner, hide_workout_sets_steps=True)

        assert steps_service.list_for_activity(activity, follower.id, db).total == 0
        assert steps_service.list_for_activity(activity, None, db).total == 0
        assert steps_service.list_for_activity(activity, owner.id, db).total == 1


class TestPublicRead:
    @pytest.fixture(autouse=True)
    def _links_on(self, db):
        edit_server_settings(db, public_shareable_links=True)

    def test_the_steps_of_a_public_activity_are_served(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PUBLIC)

        [step] = steps_service.list_public_activity_workout_steps(activity.id, db).items

        assert step.notes == "easy"

    @pytest.mark.parametrize("visibility", [_VISIBILITY.FOLLOWERS, _VISIBILITY.PRIVATE])
    def test_an_activity_that_is_not_public_serves_no_steps(self, db, owner, visibility):
        activity = _shared(db, owner, visibility)

        assert steps_service.list_public_activity_workout_steps(activity.id, db).items == []

    def test_a_hidden_activity_and_a_hidden_collection_serve_no_steps(self, db, owner):
        hidden = _shared(db, owner, _VISIBILITY.PUBLIC, is_hidden=True)
        collapsed = _shared(
            db,
            owner,
            _VISIBILITY.PUBLIC,
            hide_workout_sets_steps=True,
            start_time=DEFAULT_START.replace(day=12),
            end_time=DEFAULT_START.replace(day=12, hour=9),
        )

        assert steps_service.list_public_activity_workout_steps(hidden.id, db).total == 0
        assert steps_service.list_public_activity_workout_steps(collapsed.id, db).total == 0

    def test_turning_public_links_off_serves_no_steps(self, db, owner):
        activity = _shared(db, owner, _VISIBILITY.PUBLIC)
        edit_server_settings(db, public_shareable_links=False)

        assert steps_service.list_public_activity_workout_steps(activity.id, db).items == []
