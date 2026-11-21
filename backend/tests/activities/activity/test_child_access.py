"""Who may read an activity's child collections, on the real database: the shared gate and the child page read."""

from datetime import UTC, datetime

import pytest

import modules.activities.activity.child_access_service as child_access
import modules.activities.activity.child_collection_service as child_collection
import modules.activities.activity.constants as activity_constants
import modules.activities.activity_laps.crud as laps_crud
import modules.activities.activity_laps.schema as laps_schema
from tests._factories.activities import make_activity
from tests._factories.followers import make_follow
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user

_Visibility = activity_constants.ActivityVisibility
_START = datetime(2026, 7, 15, 9, tzinfo=UTC)

_LAPS = child_collection.ChildCollection(
    name="laps",
    hide_attr="hide_laps",
    fetch=laps_crud.get_activity_laps,
    count=laps_crud.count_activity_laps,
    build=laps_schema.ActivityLapsPage.build,
    fields_by_hide_flag={"hide_hr": ("avg_heart_rate", "max_heart_rate"), "hide_start_time": ("start_time",)},
)


@pytest.fixture
def owner(db):
    return make_user(db, timezone="UTC")


@pytest.fixture
def viewer(db):
    return make_user(db, timezone="UTC")


def _with_laps(db, owner, count=1, **fields):
    activity = make_activity(db, owner.id, **fields)
    laps_crud.create_activity_laps(
        [{"start_time": _START, "avg_heart_rate": 150, "max_heart_rate": 180, "total_distance": 1000.0}] * count,
        activity.id,
        db,
    )
    return activity


class TestVisibleFollowees:
    def test_only_accepted_followees_with_a_visible_account_are_listed(self, db, viewer):
        accepted = make_user(db)
        pending = make_user(db)
        make_follow(db, viewer.id, accepted.id, accepted=True)
        make_follow(db, viewer.id, pending.id, accepted=False)

        assert child_access.list_visible_followee_ids(viewer.id, db) == [accepted.id]

    def test_nobody_followed_is_an_empty_list(self, db, viewer):
        assert child_access.list_visible_followee_ids(viewer.id, db) == []

    def test_a_followee_who_is_inactive_or_awaiting_approval_is_left_out(self, db, viewer):
        inactive = make_user(db, active=False)
        pending = make_user(db, active=False, pending_admin_approval=True)
        for followee in (inactive, pending):
            make_follow(db, viewer.id, followee.id, accepted=True)

        assert child_access.list_visible_followee_ids(viewer.id, db) == []


class TestOwnerVisibility:
    def test_an_active_owner_is_visible_to_anyone_and_a_missing_one_to_nobody(self, db, owner, viewer):
        assert child_access.is_owner_visible_to(owner.id, viewer.id, db) is True
        assert child_access.is_owner_visible_to(owner.id, None, db) is True
        assert child_access.is_owner_visible_to(None, viewer.id, db) is False

    @pytest.mark.parametrize("state", [{"active": False}, {"active": False, "pending_admin_approval": True}])
    def test_an_owner_who_is_inactive_or_awaiting_approval_is_visible_to_themselves_only(self, db, viewer, state):
        gone = make_user(db, **state)

        assert child_access.is_owner_visible_to(gone.id, gone.id, db) is True
        assert child_access.is_owner_visible_to(gone.id, viewer.id, db) is False
        assert child_access.is_owner_visible_to(gone.id, None, db) is False


class TestParents:
    def test_the_readable_parent_is_unmasked_so_the_caller_can_read_its_flags(self, db, owner, viewer):
        parent = make_activity(db, owner.id, visibility=_Visibility.PUBLIC, hide_laps=True, private_notes="n")

        read = child_access.resolve_readable_parent(parent.id, viewer.id, db)

        assert (read.hide_laps, read.private_notes) == (True, "n")

    def test_a_private_parent_is_readable_by_its_owner_only(self, db, owner, viewer):
        parent = make_activity(db, owner.id)

        assert child_access.resolve_readable_parent(parent.id, viewer.id, db) is None
        assert child_access.resolve_readable_parent(parent.id, owner.id, db).id == parent.id

    def test_a_follower_has_the_followers_parent_of_an_active_owner_but_not_of_an_inactive_one(self, db, viewer):
        active = make_user(db)
        inactive = make_user(db, active=False)
        for followee in (active, inactive):
            make_follow(db, viewer.id, followee.id, accepted=True)
        readable = make_activity(db, active.id, visibility=_Visibility.FOLLOWERS)
        gone = make_activity(db, inactive.id, visibility=_Visibility.FOLLOWERS)

        assert child_access.resolve_readable_parent(readable.id, viewer.id, db) is not None
        assert child_access.resolve_readable_parent(gone.id, viewer.id, db) is None

    def test_the_public_parent_needs_shared_links_a_public_activity_and_a_visible_owner(self, db, owner):
        public = make_activity(db, owner.id, visibility=_Visibility.PUBLIC, private_notes="n")
        private = make_activity(db, owner.id)

        assert child_access.resolve_public_parent(public.id, db) is None
        edit_server_settings(db, public_shareable_links=True)

        assert child_access.resolve_public_parent(public.id, db).private_notes is None
        assert child_access.resolve_public_parent(private.id, db) is None

    def test_the_public_parent_of_an_inactive_owner_is_refused(self, db):
        edit_server_settings(db, public_shareable_links=True)
        gone = make_user(db, active=False)
        parent = make_activity(db, gone.id, visibility=_Visibility.PUBLIC)

        assert child_access.resolve_public_parent(parent.id, db) is None


class TestIsHiddenFrom:
    @pytest.fixture
    def parent(self, db, owner):
        return make_activity(db, owner.id, hide_laps=True)

    def test_the_owner_is_never_hidden_from(self, parent, owner):
        assert child_access.is_hidden_from(parent, owner.id, hide_attr="hide_laps") is False

    def test_another_user_and_an_anonymous_viewer_are_hidden_from_when_the_flag_is_set(self, parent, viewer):
        assert child_access.is_hidden_from(parent, viewer.id, hide_attr="hide_laps") is True
        assert child_access.is_hidden_from(parent, None, hide_attr="hide_laps") is True

    def test_nobody_is_hidden_from_when_the_flag_is_unset(self, db, owner, viewer):
        open_parent = make_activity(db, owner.id, hide_laps=False)

        assert child_access.is_hidden_from(open_parent, viewer.id, hide_attr="hide_laps") is False
        assert child_access.is_hidden_from(open_parent, None, hide_attr="hide_laps") is False


class TestChildCollectionForASignedInCaller:
    def _page(self, db, activity, requester, **kwargs):
        return _LAPS.list_for_requester(
            activity.id, requester.id, db, page_number=kwargs.get("page_number", 1), num_records=kwargs.get("n", 200)
        )

    def test_a_viewer_gets_a_page_with_the_total_across_every_page(self, db, owner, viewer):
        activity = _with_laps(db, owner, count=3, visibility=_Visibility.PUBLIC)

        first = self._page(db, activity, viewer, n=2)
        last = self._page(db, activity, viewer, n=2, page_number=2)

        assert (len(first.items), first.total, first.next) == (2, 3, 2)
        assert (len(last.items), last.next) == (1, None)

    def test_a_parent_the_caller_may_not_see_answers_with_the_empty_page_of_a_parent_without_laps(
        self, db, owner, viewer
    ):
        private = _with_laps(db, owner)
        bare = make_activity(db, owner.id, visibility=_Visibility.PUBLIC)

        refused = self._page(db, private, viewer)
        none = self._page(db, bare, viewer)

        assert refused.model_dump() == none.model_dump()

    def test_the_hide_flag_refuses_a_non_owner_but_not_the_owner(self, db, owner, viewer):
        activity = _with_laps(db, owner, visibility=_Visibility.PUBLIC, hide_laps=True)

        assert self._page(db, activity, viewer).total == 0
        assert self._page(db, activity, owner).total == 1

    def test_a_non_owner_gets_the_fields_the_parent_hides_cleared_and_the_owner_gets_them_whole(
        self, db, owner, viewer
    ):
        activity = _with_laps(db, owner, visibility=_Visibility.PUBLIC, hide_hr=True, hide_start_time=True)

        seen = self._page(db, activity, viewer).items[0]
        own = self._page(db, activity, owner).items[0]

        assert (seen.avg_heart_rate, seen.max_heart_rate, seen.start_time, seen.total_distance) == (
            None,
            None,
            None,
            1000.0,
        )
        assert (own.avg_heart_rate, own.start_time) == (150, _START)

    def test_a_flag_that_is_unset_clears_nothing(self, db, owner, viewer):
        activity = _with_laps(db, owner, visibility=_Visibility.PUBLIC)

        item = self._page(db, activity, viewer).items[0]

        assert (item.avg_heart_rate, item.start_time) == (150, _START)

    def test_a_collection_declaring_no_fields_serves_the_rows_as_they_are(self, db, owner, viewer):
        activity = _with_laps(db, owner, visibility=_Visibility.PUBLIC, hide_hr=True)
        plain = child_collection.ChildCollection(
            name="laps",
            hide_attr="hide_laps",
            fetch=laps_crud.get_activity_laps,
            count=laps_crud.count_activity_laps,
            build=laps_schema.ActivityLapsPage.build,
        )

        page = plain.list_for_requester(activity.id, viewer.id, db, page_number=1, num_records=10)

        assert page.items[0].avg_heart_rate == 150


class TestChildCollectionForAnAnonymousViewer:
    def _public(self, db, activity):
        return _LAPS.list_public(activity.id, db, page_number=1, num_records=200)

    def test_a_public_activitys_page_is_served_masked_once_links_are_shared(self, db, owner):
        activity = _with_laps(db, owner, visibility=_Visibility.PUBLIC, hide_hr=True)
        assert self._public(db, activity).total == 0
        edit_server_settings(db, public_shareable_links=True)

        page = self._public(db, activity)

        assert (page.total, page.items[0].avg_heart_rate, page.items[0].total_distance) == (1, None, 1000.0)

    def test_a_non_public_parent_and_a_hidden_collection_answer_with_the_empty_page(self, db, owner):
        edit_server_settings(db, public_shareable_links=True)
        private = _with_laps(db, owner)
        hidden = _with_laps(db, owner, visibility=_Visibility.PUBLIC, hide_laps=True)

        assert self._public(db, private).total == 0
        assert self._public(db, hidden).total == 0
