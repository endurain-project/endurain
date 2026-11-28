"""What a reader gets from the activity queries: visibility, filters, order, paging and masking, on PostgreSQL."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

import modules.activities.activity.constants as activity_constants
import modules.activities.activity.crud as activity_crud
from tests._factories.activities import make_activity, make_activity_at, set_activity_created_at
from tests._factories.gears import make_gear
from tests._factories.users import make_user

_Visibility = activity_constants.ActivityVisibility
_Type = activity_constants.ActivityType
_DAY = datetime(2026, 7, 15, 9, tzinfo=UTC)


@pytest.fixture
def owner(db):
    return make_user(db, timezone="UTC")


@pytest.fixture
def viewer(db):
    return make_user(db, timezone="UTC")


def _listed(db, owner_id, *, is_owner=False, followees=None, **filters):
    """The ids of the activities a reader gets on the first page, and the count that goes with them."""
    items = activity_crud.get_user_activities_with_pagination(
        owner_id, db, num_records=50, user_is_owner=is_owner, followee_ids=followees, **filters
    )
    total = activity_crud.count_user_activities(owner_id, db, user_is_owner=is_owner, followee_ids=followees, **filters)
    assert total == len(items)
    return [item.id for item in items]


class TestWhoSeesWhat:
    @pytest.fixture
    def activities(self, db, owner):
        return {
            "public": make_activity_at(db, owner.id, _DAY, visibility=_Visibility.PUBLIC).id,
            "followers": make_activity_at(db, owner.id, _DAY + timedelta(hours=2), visibility=_Visibility.FOLLOWERS).id,
            "private": make_activity_at(db, owner.id, _DAY + timedelta(hours=4), visibility=_Visibility.PRIVATE).id,
        }

    def test_the_owner_lists_every_visibility(self, db, owner, activities):
        assert set(_listed(db, owner.id, is_owner=True)) == set(activities.values())

    def test_an_anonymous_reader_lists_only_the_public_activity(self, db, owner, activities):
        assert _listed(db, owner.id) == [activities["public"]]

    def test_a_reader_who_does_not_follow_lists_only_the_public_activity(self, db, owner, viewer, activities):
        assert _listed(db, owner.id, followees=[]) == [activities["public"]]

    def test_an_accepted_follower_also_lists_the_followers_activity(self, db, owner, activities):
        assert set(_listed(db, owner.id, followees=[owner.id])) == {activities["public"], activities["followers"]}

    def test_a_followee_of_someone_else_does_not_open_the_followers_activity(self, db, owner, viewer, activities):
        assert _listed(db, owner.id, followees=[viewer.id]) == [activities["public"]]

    def test_a_hidden_activity_is_listed_for_the_owner_only(self, db, owner):
        hidden = make_activity(db, owner.id, visibility=_Visibility.PUBLIC, is_hidden=True)

        assert _listed(db, owner.id, is_owner=True) == [hidden.id]
        assert _listed(db, owner.id) == []

    def test_an_activity_synced_from_the_strava_api_is_the_owners_alone(self, db, owner):
        synced = make_activity(db, owner.id, visibility=_Visibility.PUBLIC, strava_activity_id=42)

        assert _listed(db, owner.id, is_owner=True) == [synced.id]
        assert _listed(db, owner.id) == []

    def test_only_the_owners_own_activities_are_listed(self, db, owner, viewer):
        make_activity(db, viewer.id, visibility=_Visibility.PUBLIC)

        assert _listed(db, owner.id, is_owner=True) == []

    def test_a_non_owner_reads_the_activity_without_what_the_owner_hid(self, db, owner):
        make_activity(
            db,
            owner.id,
            visibility=_Visibility.PUBLIC,
            private_notes="for me",
            city="Porto",
            country="Portugal",
            average_hr=150,
            hide_location=True,
            hide_hr=True,
            strava_gear_id="g1",
        )

        [item] = activity_crud.get_user_activities(owner.id, db, user_is_owner=False)

        assert (item.city, item.country, item.timezone, item.average_hr) == (None, None, None, None)
        assert (item.private_notes, item.strava_gear_id, item.import_info) == (None, None, None)

    def test_the_owner_reads_the_activity_whole(self, db, owner):
        make_activity(db, owner.id, private_notes="for me", city="Porto", average_hr=150, hide_location=True)

        [item] = activity_crud.get_user_activities(owner.id, db, user_is_owner=True)

        assert (item.private_notes, item.city, item.average_hr) == ("for me", "Porto", 150)


class TestHiddenStartTime:
    def test_a_date_window_does_not_reveal_a_hidden_start_to_a_reader(self, db, owner):
        make_activity_at(db, owner.id, _DAY, visibility=_Visibility.PUBLIC, hide_start_time=True)

        assert _listed(db, owner.id, start_date=_DAY.date(), end_date=_DAY.date()) == []

    def test_the_owner_finds_a_hidden_start_by_its_date(self, db, owner):
        hidden = make_activity_at(db, owner.id, _DAY, hide_start_time=True)

        assert _listed(db, owner.id, is_owner=True, start_date=_DAY.date(), end_date=_DAY.date()) == [hidden.id]

    def test_without_a_window_a_reader_still_lists_it_with_the_times_cleared(self, db, owner):
        make_activity_at(db, owner.id, _DAY, visibility=_Visibility.PUBLIC, hide_start_time=True)

        [item] = activity_crud.get_user_activities(owner.id, db, user_is_owner=False)

        assert (item.start_time, item.end_time, item.created_at, item.updated_at) == (None, None, None, None)


class TestFilters:
    def test_the_date_window_follows_the_activitys_own_local_day_at_both_ends(self, db, owner):
        # 23:30 UTC on 14 July is already 15 July in Auckland, and 22:30 UTC on 15 July is already 16 July there.
        early = make_activity_at(db, owner.id, datetime(2026, 7, 14, 23, 30, tzinfo=UTC), timezone="Pacific/Auckland")
        late = make_activity_at(db, owner.id, datetime(2026, 7, 15, 22, 30, tzinfo=UTC), timezone="Pacific/Auckland")

        on_the_15th = _listed(db, owner.id, is_owner=True, start_date=date(2026, 7, 15), end_date=date(2026, 7, 15))

        assert on_the_15th == [early.id]
        assert late.id in _listed(db, owner.id, is_owner=True, start_date=date(2026, 7, 16))

    def test_the_type_filter_keeps_the_type_asked_for(self, db, owner):
        run = make_activity_at(db, owner.id, _DAY, activity_type=_Type.RUN.stored)
        make_activity_at(db, owner.id, _DAY + timedelta(hours=3), activity_type=_Type.RIDE.stored)

        assert _listed(db, owner.id, is_owner=True, activity_type=_Type.RUN) == [run.id]

    def test_a_gear_filter_keeps_only_that_gears_activities_and_counts_them(self, db, owner, viewer):
        mine = make_gear(db, owner.id, nickname="Mine")
        make_gear(db, viewer.id, nickname="Theirs")
        on_gear = make_activity_at(db, owner.id, _DAY, gear_id=mine.id)
        make_activity_at(db, owner.id, _DAY + timedelta(hours=3))

        assert _listed(db, owner.id, is_owner=True, gear_id=mine.id) == [on_gear.id]

    def test_a_name_search_ignores_case_and_a_location_hidden_from_the_reader_is_not_searched(self, db, owner):
        named = make_activity_at(db, owner.id, _DAY, name="Evening Tempo", visibility=_Visibility.PUBLIC)
        located = make_activity_at(
            db,
            owner.id,
            _DAY + timedelta(hours=3),
            name="Plain",
            city="Lisbon",
            hide_location=True,
            visibility=_Visibility.PUBLIC,
        )

        assert _listed(db, owner.id, name_search="tempo") == [named.id]
        assert _listed(db, owner.id, name_search="lisbon") == []
        assert _listed(db, owner.id, is_owner=True, name_search="lisbon") == [located.id]

    def test_the_filters_apply_together(self, db, owner):
        wanted = make_activity_at(db, owner.id, _DAY, name="Long run", activity_type=_Type.RUN.stored)
        make_activity_at(db, owner.id, _DAY + timedelta(hours=3), name="Long ride", activity_type=_Type.RIDE.stored)
        make_activity_at(db, owner.id, _DAY - timedelta(days=9), name="Long run", activity_type=_Type.RUN.stored)

        found = _listed(
            db,
            owner.id,
            is_owner=True,
            activity_type=_Type.RUN,
            name_search="long",
            start_date=date(2026, 7, 10),
        )

        assert found == [wanted.id]

    def test_the_list_of_all_matches_comes_newest_first(self, db, owner):
        old = make_activity_at(db, owner.id, _DAY)
        new = make_activity_at(db, owner.id, _DAY + timedelta(days=1))

        assert [item.id for item in activity_crud.get_user_activities(owner.id, db, user_is_owner=True)] == [
            new.id,
            old.id,
        ]


class TestOrderAndPaging:
    def test_a_page_holds_its_slice_and_the_next_page_continues_it(self, db, owner):
        ids = [make_activity_at(db, owner.id, _DAY + timedelta(days=day)).id for day in range(5)]

        first = activity_crud.get_user_activities_with_pagination(
            owner.id, db, page_number=1, num_records=2, user_is_owner=True
        )
        last = activity_crud.get_user_activities_with_pagination(
            owner.id, db, page_number=3, num_records=2, user_is_owner=True
        )

        assert [item.id for item in first] == [ids[4], ids[3]]
        assert [item.id for item in last] == [ids[0]]

    def test_a_page_beyond_the_end_is_empty(self, db, owner):
        make_activity(db, owner.id)

        assert (
            activity_crud.get_user_activities_with_pagination(
                owner.id, db, page_number=2, num_records=5, user_is_owner=True
            )
            == []
        )

    def test_an_activity_with_no_value_sorts_last_in_either_direction(self, db, owner):
        none = make_activity_at(db, owner.id, _DAY, distance=0, calories=None)
        low = make_activity_at(db, owner.id, _DAY + timedelta(days=1), calories=100)
        high = make_activity_at(db, owner.id, _DAY + timedelta(days=2), calories=900)

        by = {
            order: [
                item.id
                for item in activity_crud.get_user_activities_with_pagination(
                    owner.id, db, sort_by="calories", sort_order=order, user_is_owner=True
                )
            ]
            for order in ("asc", "desc")
        }

        assert by["desc"] == [high.id, low.id, none.id]
        assert by["asc"] == [low.id, high.id, none.id]

    def test_an_activity_with_no_place_sorts_as_the_empty_text_by_location(self, db, owner):
        placed = make_activity_at(db, owner.id, _DAY, country="Portugal", city="Porto")
        unplaced = make_activity_at(db, owner.id, _DAY + timedelta(days=1))

        ordered = activity_crud.get_user_activities_with_pagination(
            owner.id, db, sort_by="location", sort_order="asc", user_is_owner=True
        )

        assert [item.id for item in ordered] == [unplaced.id, placed.id]

    def test_a_reader_cannot_learn_a_hidden_value_from_the_order(self, db, owner):
        shown = make_activity_at(db, owner.id, _DAY, visibility=_Visibility.PUBLIC, elevation_gain=10)
        hidden = make_activity_at(
            db,
            owner.id,
            _DAY + timedelta(days=1),
            visibility=_Visibility.PUBLIC,
            elevation_gain=5000,
            hide_elevation=True,
        )

        as_reader = activity_crud.get_user_activities_with_pagination(
            owner.id, db, sort_by="elevation", sort_order="desc", user_is_owner=False
        )
        as_owner = activity_crud.get_user_activities_with_pagination(
            owner.id, db, sort_by="elevation", sort_order="desc", user_is_owner=True
        )

        assert [item.id for item in as_reader] == [shown.id, hidden.id]
        assert [item.id for item in as_owner] == [hidden.id, shown.id]

    def test_activities_with_equal_values_keep_a_stable_order_across_pages(self, db, owner):
        ids = sorted(make_activity_at(db, owner.id, _DAY + timedelta(hours=h), distance=5).id for h in range(0, 8, 2))

        pages = [
            activity_crud.get_user_activities_with_pagination(
                owner.id, db, page_number=n, num_records=2, sort_by="distance", sort_order="asc", user_is_owner=True
            )
            for n in (1, 2)
        ]

        assert [item.id for page in pages for item in page] == ids


class TestSingleReads:
    @pytest.fixture
    def public(self, db, owner):
        return make_activity(
            db, owner.id, visibility=_Visibility.PUBLIC, private_notes="mine", hide_hr=True, average_hr=1
        )

    def test_the_owner_reads_their_activity_whole(self, db, owner, public):
        read = activity_crud.get_activity_by_id_from_user_id_or_has_visibility(public.id, owner.id, db)

        assert (read.private_notes, read.average_hr) == ("mine", 1)

    def test_another_user_reads_a_public_activity_masked(self, db, viewer, public):
        read = activity_crud.get_activity_by_id_from_user_id_or_has_visibility(public.id, viewer.id, db)

        assert (read.id, read.private_notes, read.average_hr) == (public.id, None, None)

    def test_another_user_cannot_read_a_private_activity(self, db, owner, viewer):
        private = make_activity(db, owner.id)

        assert activity_crud.get_activity_by_id_from_user_id_or_has_visibility(private.id, viewer.id, db) is None

    def test_a_follower_reads_a_followers_activity_only_when_the_follow_is_passed_in(self, db, owner, viewer):
        followers = make_activity(db, owner.id, visibility=_Visibility.FOLLOWERS)

        assert activity_crud.get_activity_by_id_from_user_id_or_has_visibility(followers.id, viewer.id, db) is None
        read = activity_crud.get_activity_by_id_from_user_id_or_has_visibility(
            followers.id, viewer.id, db, followee_ids=[owner.id]
        )
        assert read is not None

    def test_the_viewable_read_keeps_the_hide_flags_for_the_caller_to_apply(self, db, viewer, public):
        read = activity_crud.get_viewable_activity_by_id_for_user(public.id, viewer.id, db)

        assert (read.hide_hr, read.average_hr, read.private_notes) == (True, 1, "mine")

    def test_the_viewable_read_refuses_a_private_activity_to_another_user(self, db, owner, viewer):
        private = make_activity(db, owner.id)

        assert activity_crud.get_viewable_activity_by_id_for_user(private.id, viewer.id, db) is None
        assert activity_crud.get_viewable_activity_by_id_for_user(private.id, owner.id, db) is not None

    def test_the_public_read_masks_and_refuses_what_is_not_public(self, db, owner, public):
        private = make_activity(db, owner.id)
        hidden = make_activity(db, owner.id, visibility=_Visibility.PUBLIC, is_hidden=True)

        read = activity_crud.get_activity_by_id_if_is_public(public.id, db)

        assert (read.private_notes, read.average_hr) == (None, None)
        assert activity_crud.get_activity_by_id_if_is_public(private.id, db) is None
        assert activity_crud.get_activity_by_id_if_is_public(hidden.id, db) is None
        assert activity_crud.get_activity_by_id_if_is_public(uuid.uuid4(), db) is None

    def test_the_lookups_by_owner_find_only_the_users_own_activity(self, db, owner, viewer):
        mine = make_activity(db, owner.id)

        assert activity_crud.get_activity_by_id(mine.id, db).id == mine.id
        assert activity_crud.get_activity_by_id(uuid.uuid4(), db) is None
        assert activity_crud.get_activity_by_id_from_user_id(mine.id, owner.id, db).id == mine.id
        assert activity_crud.get_activity_by_id_from_user_id(mine.id, viewer.id, db) is None

    def test_which_of_some_ids_exist(self, db, owner):
        mine = make_activity(db, owner.id)
        gone = uuid.uuid4()

        assert activity_crud.get_existing_activity_ids([mine.id, gone], db) == {mine.id}
        assert activity_crud.get_existing_activity_ids([], db) == set()

    def test_the_activity_types_a_user_recorded_come_in_stored_order(self, db, owner, viewer):
        make_activity_at(db, owner.id, _DAY, activity_type=_Type.RIDE.stored)
        make_activity_at(db, owner.id, _DAY + timedelta(hours=3), activity_type=_Type.RUN.stored)
        make_activity_at(db, owner.id, _DAY + timedelta(hours=6), activity_type=_Type.RUN.stored)
        make_activity(db, viewer.id, activity_type=_Type.YOGA.stored)

        assert activity_crud.get_distinct_activity_types_for_user(owner.id, db) == [_Type.RUN, _Type.RIDE]


class TestFeeds:
    def _own(self, db, user_id, size=10):
        return [entry.activity.id for entry in activity_crud.get_own_feed_after(user_id, None, size, db)]

    def _walk(self, db, fetch, size):
        """Read a whole feed in slices of ``size``, resuming after each slice's last entry as the service does."""
        seen: list[list[uuid.UUID]] = []
        after = None
        while True:
            entries = fetch(after, size + 1)
            page = entries[:size]
            seen.append([entry.activity.id for entry in page])
            if len(entries) <= size:
                return seen
            after = (page[-1].cursor_sort_value, page[-1].cursor_id)

    def test_the_own_feed_lists_every_visibility_newest_first_and_nobody_elses(self, db, owner, viewer):
        private = make_activity_at(db, owner.id, _DAY, visibility=_Visibility.PRIVATE)
        public = make_activity_at(db, owner.id, _DAY + timedelta(hours=4), visibility=_Visibility.PUBLIC)
        followers = make_activity_at(db, owner.id, _DAY + timedelta(hours=2), visibility=_Visibility.FOLLOWERS)
        make_activity_at(db, viewer.id, _DAY + timedelta(hours=6))

        assert self._own(db, owner.id) == [public.id, followers.id, private.id]

    def test_the_cursor_walks_every_activity_once_across_slices(self, db, owner):
        ids = [make_activity_at(db, owner.id, _DAY + timedelta(hours=h)).id for h in range(5)]

        walked = self._walk(db, lambda after, n: activity_crud.get_own_feed_after(owner.id, after, n, db), 2)

        assert walked == [[ids[4], ids[3]], [ids[2], ids[1]], [ids[0]]]

    def test_activities_sharing_a_start_time_are_neither_skipped_nor_repeated(self, db, owner):
        ids = [make_activity_at(db, owner.id, _DAY).id for _ in range(4)]

        walked = self._walk(db, lambda after, n: activity_crud.get_own_feed_after(owner.id, after, n, db), 2)

        assert [i for page in walked for i in page] == sorted(ids, reverse=True)

    def test_a_hidden_start_is_placed_by_when_the_activity_was_recorded(self, db, owner):
        late = make_activity_at(db, owner.id, _DAY + timedelta(hours=5))
        hidden = make_activity_at(db, owner.id, _DAY, hide_start_time=True)
        set_activity_created_at(db, hidden.id, _DAY + timedelta(hours=9))

        assert self._own(db, owner.id) == [hidden.id, late.id]

    def test_the_owner_sees_the_hidden_start_of_their_own_activity_in_the_feed(self, db, owner):
        hidden = make_activity_at(db, owner.id, _DAY, hide_start_time=True)

        [entry] = activity_crud.get_own_feed_after(owner.id, None, 10, db)

        assert (entry.activity.id, entry.activity.start_time) == (hidden.id, _DAY)

    def test_the_following_feed_lists_public_and_followers_activities_of_the_followees_masked(self, db, owner, viewer):
        public = make_activity_at(db, owner.id, _DAY, visibility=_Visibility.PUBLIC, private_notes="n")
        followers = make_activity_at(db, owner.id, _DAY + timedelta(hours=3), visibility=_Visibility.FOLLOWERS)
        make_activity_at(db, owner.id, _DAY + timedelta(hours=6), visibility=_Visibility.PRIVATE)
        make_activity_at(db, owner.id, _DAY + timedelta(hours=7), visibility=_Visibility.PUBLIC, is_hidden=True)
        make_activity_at(db, owner.id, _DAY + timedelta(hours=8), visibility=_Visibility.PUBLIC, strava_activity_id=1)
        make_activity_at(db, viewer.id, _DAY + timedelta(hours=9), visibility=_Visibility.PUBLIC)

        entries = activity_crud.get_following_feed_after([owner.id], None, 10, db)

        assert [entry.activity.id for entry in entries] == [followers.id, public.id]
        assert entries[1].activity.private_notes is None

    def test_a_user_without_activities_has_an_empty_own_feed(self, db, owner):
        assert activity_crud.get_own_feed_after(owner.id, None, 10, db) == []

    def test_a_user_who_follows_nobody_has_an_empty_following_feed(self, db, owner):
        make_activity(db, owner.id, visibility=_Visibility.PUBLIC)

        assert activity_crud.get_following_feed_after([], None, 10, db) == []
