"""The activity service on the real database: stats by the reader's local day, paged reads, the feed and the edits."""

import uuid
from datetime import UTC, datetime, timedelta

import jasil.runtime as jasil_runtime
import pytest
from sqlalchemy import update

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.activities.activity.audit_actions as activity_audit_actions
import modules.activities.activity.constants as activity_constants
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.events as activity_events
import modules.activities.activity.models as activity_models
import modules.activities.activity.schema as activity_schema
import modules.activities.activity.service as activity_service
import modules.users.users.models as users_models
from tests._factories.activities import make_activity, make_activity_at, make_activity_media
from tests._factories.followers import make_follow
from tests._factories.gears import make_gear
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import audit_rows_of, make_user

_Visibility = activity_constants.ActivityVisibility
_Period = activity_constants.StatsPeriod
_DAY = datetime(2026, 7, 15, 9, tzinfo=UTC)


@pytest.fixture
def owner(db):
    return make_user(db, timezone="UTC")


@pytest.fixture
def viewer(db):
    return make_user(db, timezone="UTC")


def _deactivate(db, user) -> None:
    """Deactivate an account after others followed it, as an administrator would."""
    db.execute(update(users_models.Users).where(users_models.Users.id == user.id).values(active=False))
    db.flush()


def _set_now(moment: datetime) -> None:
    """Make the platform clock, which decides every user's "today", read ``moment``."""
    jasil_runtime.get_active_platform().clock.moment = moment


class TestStatsByTheReadersLocalDay:
    def test_the_week_is_the_one_holding_the_readers_local_today_not_utc_today(self, db):
        # Sunday 19 July 23:30 UTC is already Monday 20 July in Auckland, which opens a new Monday-first week.
        _set_now(datetime(2026, 7, 19, 23, 30, tzinfo=UTC))
        in_utc = make_user(db, timezone="UTC")
        in_auckland = make_user(db, timezone="Pacific/Auckland")
        for user in (in_utc, in_auckland):
            make_activity_at(db, user.id, datetime(2026, 7, 19, 10, tzinfo=UTC), timezone="UTC", distance=5000)

        utc_week = activity_service.period_stats(in_utc.id, _Period.WEEK, in_utc.id, db)
        auckland_week = activity_service.period_stats(in_auckland.id, _Period.WEEK, in_auckland.id, db)

        assert utc_week.run.distance == 5000.0
        assert auckland_week.run.distance == 0.0

    def test_the_month_follows_the_readers_local_today_the_same_way(self, db):
        _set_now(datetime(2026, 7, 31, 23, 30, tzinfo=UTC))
        in_utc = make_user(db, timezone="UTC")
        in_auckland = make_user(db, timezone="Pacific/Auckland")
        for user in (in_utc, in_auckland):
            make_activity_at(db, user.id, datetime(2026, 7, 31, 10, tzinfo=UTC), timezone="UTC")

        assert activity_service.period_stats(in_utc.id, _Period.MONTH, in_utc.id, db).run.distance == 10000.0
        assert activity_service.period_stats(in_auckland.id, _Period.MONTH, in_auckland.id, db).run.distance == 0.0

    def test_a_date_the_caller_sends_decides_the_period_instead_of_the_clock(self, db, owner):
        _set_now(datetime(2026, 1, 5, 12, tzinfo=UTC))
        make_activity_at(db, owner.id, datetime(2026, 7, 15, 10, tzinfo=UTC))

        stats = activity_service.period_stats(owner.id, _Period.WEEK, owner.id, db, anchor=datetime(2026, 7, 16).date())

        assert stats.run.distance == 10000.0

    def test_a_week_starts_on_the_readers_first_day_of_the_week(self, db):
        _set_now(datetime(2026, 7, 15, 12, tzinfo=UTC))  # a Wednesday
        sunday_first = make_user(db, timezone="UTC", first_day_of_week="sunday")
        monday_first = make_user(db, timezone="UTC")
        for user in (sunday_first, monday_first):
            make_activity_at(db, user.id, datetime(2026, 7, 12, 10, tzinfo=UTC))

        assert activity_service.week_stats(sunday_first.id, sunday_first.id, db).run.distance == 10000.0
        assert activity_service.week_stats(monday_first.id, monday_first.id, db).run.distance == 0.0

    def test_stats_are_per_sport_and_empty_when_nothing_was_recorded(self, db, owner):
        _set_now(_DAY)
        make_activity_at(db, owner.id, _DAY, activity_type=4, distance=30000, total_timer_time=5400.0, calories=700)
        make_activity_at(db, owner.id, _DAY + timedelta(hours=3), activity_type=1, distance=5000)

        stats = activity_service.period_stats(owner.id, _Period.WEEK, owner.id, db)

        assert (stats.bike.distance, stats.bike.time, stats.bike.calories) == (30000.0, 5400.0, 700.0)
        assert stats.run.distance == 5000.0
        assert (
            activity_service.month_stats(owner.id, owner.id, db, anchor=datetime(2020, 1, 1).date()).run.distance == 0
        )

    def test_another_users_stats_hold_only_what_the_reader_may_see(self, db, owner, viewer):
        _set_now(_DAY)
        make_activity_at(db, owner.id, _DAY, visibility=_Visibility.PUBLIC, distance=1000)
        make_activity_at(db, owner.id, _DAY + timedelta(hours=3), visibility=_Visibility.FOLLOWERS, distance=2000)
        make_activity_at(db, owner.id, _DAY + timedelta(hours=6), visibility=_Visibility.PRIVATE, distance=4000)

        before = activity_service.period_stats(owner.id, _Period.WEEK, viewer.id, db).run.distance
        make_follow(db, viewer.id, owner.id, accepted=True)
        after = activity_service.period_stats(owner.id, _Period.WEEK, viewer.id, db).run.distance

        assert (before, after) == (1000.0, 3000.0)

    @pytest.mark.parametrize("state", [{"active": False}, {"pending_admin_approval": True, "active": False}])
    def test_the_stats_of_an_owner_who_is_inactive_or_awaiting_approval_are_not_found(self, db, viewer, state):
        gone = make_user(db, **state)

        with pytest.raises(core_exceptions.NotFoundError):
            activity_service.period_stats(gone.id, _Period.WEEK, viewer.id, db)

    def test_the_owners_own_stats_are_not_held_to_their_own_visibility(self, db):
        _set_now(_DAY)
        inactive = make_user(db, active=False)

        assert activity_service.period_stats(inactive.id, _Period.WEEK, inactive.id, db).run.distance == 0

    def test_a_requester_who_does_not_exist_is_not_found(self, db, owner):
        with pytest.raises(core_exceptions.NotFoundError):
            activity_service.week_stats(owner.id, uuid.uuid4(), db)


class TestProfileSummary:
    def test_it_holds_both_periods_and_the_count_of_what_the_reader_sees_this_month(self, db, owner, viewer):
        _set_now(_DAY)
        make_activity_at(db, owner.id, _DAY, visibility=_Visibility.PUBLIC, distance=1000)
        make_activity_at(db, owner.id, _DAY + timedelta(hours=3), visibility=_Visibility.PUBLIC, distance=500)
        make_activity_at(db, owner.id, _DAY + timedelta(hours=6), visibility=_Visibility.PRIVATE)
        make_activity_at(db, owner.id, _DAY - timedelta(days=40), visibility=_Visibility.PUBLIC)

        summary = activity_service.user_profile_summary(owner.id, viewer.id, db)
        own = activity_service.user_profile_summary(owner.id, owner.id, db)

        assert (summary.month_activity_count, summary.week_stats.run.distance) == (2, 1500.0)
        assert summary.month_stats.run.distance == 1500.0
        assert own.month_activity_count == 3

    def test_the_month_is_the_one_of_the_anchor_the_caller_sends(self, db, owner):
        make_activity_at(db, owner.id, datetime(2026, 3, 10, 10, tzinfo=UTC))

        summary = activity_service.user_profile_summary(owner.id, owner.id, db, anchor=datetime(2026, 3, 20).date())

        assert (summary.month_activity_count, summary.month_stats.run.distance) == (1, 10000.0)

    def test_the_activity_count_is_the_owners_own_with_the_filters_asked_for(self, db, owner):
        make_activity_at(db, owner.id, _DAY, name="Tempo run", activity_type=1)
        make_activity_at(db, owner.id, _DAY + timedelta(hours=3), name="Easy ride", activity_type=4)

        assert activity_service.count_user_activities(owner.id, db) == 2
        assert activity_service.count_user_activities(owner.id, db, name_search="tempo") == 1
        assert (
            activity_service.count_user_activities(
                owner.id, db, activity_type=activity_constants.ActivityType.RIDE, start_date=_DAY.date()
            )
            == 1
        )


class TestPages:
    def _page(self, db, owner_id, requester_id, **kwargs):
        return activity_service.page_user_activities(
            owner_id,
            requester_id,
            db,
            page_number=kwargs.pop("page_number", 1),
            num_records=kwargs.pop("num_records", 25),
            **kwargs,
        )

    def test_a_page_holds_summaries_and_a_total_that_follows_the_same_filters(self, db, owner):
        for hours in range(0, 12, 3):
            make_activity_at(db, owner.id, _DAY + timedelta(hours=hours), private_notes="secret", name=f"Run {hours}")
        make_activity_at(db, owner.id, _DAY + timedelta(hours=20), name="Ride", activity_type=4)

        page = self._page(db, owner.id, owner.id, num_records=2, name_search="run")

        assert (page.total, len(page.items), page.page, page.next) == (4, 2, 1, 2)
        assert not hasattr(page.items[0], "private_notes")
        assert not hasattr(page.items[0], "import_info")

    def test_the_owner_gets_a_thumbnail_url_and_the_photos_of_their_own_activities_only(self, db, owner, viewer):
        mine = make_activity(db, owner.id, visibility=_Visibility.PUBLIC)
        make_activity_media(db, mine, "a.jpg")
        activity_crud.set_activity_thumbnail_key(mine.id, f"{mine.id}.webp", db)

        own = self._page(db, owner.id, owner.id).items[0]
        seen = self._page(db, owner.id, viewer.id).items[0]

        assert own.map_thumbnail_url and [media.url for media in own.media]
        assert seen.map_thumbnail_url and seen.media == []

    def test_a_viewer_gets_no_thumbnail_url_for_a_map_the_owner_hid(self, db, owner, viewer):
        hidden = make_activity(db, owner.id, visibility=_Visibility.PUBLIC, hide_map=True)
        activity_crud.set_activity_thumbnail_key(hidden.id, f"{hidden.id}.webp", db)

        assert self._page(db, owner.id, viewer.id).items[0].map_thumbnail_url is None
        assert self._page(db, owner.id, owner.id).items[0].map_thumbnail_url

    def test_a_viewers_page_total_counts_only_what_the_viewer_sees(self, db, owner, viewer):
        make_activity_at(db, owner.id, _DAY, visibility=_Visibility.PUBLIC)
        make_activity_at(db, owner.id, _DAY + timedelta(hours=3), visibility=_Visibility.FOLLOWERS)
        make_activity_at(db, owner.id, _DAY + timedelta(hours=6), visibility=_Visibility.PRIVATE)

        assert self._page(db, owner.id, viewer.id).total == 1
        make_follow(db, viewer.id, owner.id, accepted=True)
        assert self._page(db, owner.id, viewer.id).total == 2
        assert self._page(db, owner.id, owner.id).total == 3

    def test_a_follow_still_pending_does_not_open_the_followers_activities(self, db, owner, viewer):
        make_activity(db, owner.id, visibility=_Visibility.FOLLOWERS)
        make_follow(db, viewer.id, owner.id, accepted=False)

        assert self._page(db, owner.id, viewer.id).total == 0

    @pytest.mark.parametrize("state", [{"active": False}, {"active": False, "pending_admin_approval": True}])
    def test_the_page_of_an_owner_who_is_inactive_or_awaiting_approval_is_not_found(self, db, viewer, state):
        gone = make_user(db, **state)
        make_activity(db, gone.id, visibility=_Visibility.PUBLIC)

        with pytest.raises(core_exceptions.NotFoundError):
            self._page(db, gone.id, viewer.id)

    def test_the_activity_types_a_user_recorded_are_listed_with_their_labels(self, db, owner):
        make_activity_at(db, owner.id, _DAY, activity_type=4)
        make_activity_at(db, owner.id, _DAY + timedelta(hours=3), activity_type=1)

        assert activity_service.list_activity_types(owner.id, db) == {
            activity_constants.ActivityType.RUN: "Run",
            activity_constants.ActivityType.RIDE: "Ride",
        }


class TestFeed:
    def test_the_following_feed_lists_accepted_followees_in_slices_with_their_profiles(self, db, owner, viewer):
        followee_a = make_user(db, timezone="UTC")
        followee_b = make_user(db, timezone="UTC")
        stranger = make_user(db, timezone="UTC")
        for followee in (followee_a, followee_b):
            make_follow(db, viewer.id, followee.id, accepted=True)
        make_follow(db, viewer.id, stranger.id, accepted=False)
        ids = [
            make_activity_at(db, user.id, _DAY + timedelta(hours=hours), visibility=_Visibility.PUBLIC).id
            for hours, user in ((0, followee_a), (3, followee_b), (6, followee_a))
        ]
        make_activity_at(db, stranger.id, _DAY + timedelta(hours=9), visibility=_Visibility.PUBLIC)
        make_activity_at(db, followee_a.id, _DAY + timedelta(hours=12), visibility=_Visibility.PRIVATE)

        first = activity_service.scroll_feed(viewer.id, None, 2, db)
        second = activity_service.scroll_feed(viewer.id, first.next_cursor, 2, db)

        assert [item.id for item in first.items] == [ids[2], ids[1]]
        assert first.next_cursor is not None
        assert [item.id for item in second.items] == [ids[0]]
        assert second.next_cursor is None
        assert set(first.users) == {followee_a.id, followee_b.id}
        assert set(second.users) == {followee_a.id}

    def test_a_followee_who_is_inactive_or_awaiting_approval_leaves_the_feed(self, db, viewer):
        followee = make_user(db, timezone="UTC")
        make_follow(db, viewer.id, followee.id, accepted=True)
        make_activity(db, followee.id, visibility=_Visibility.PUBLIC)
        _deactivate(db, followee)

        assert activity_service.scroll_feed(viewer.id, None, 10, db).items == []

    def test_the_own_feed_lists_the_callers_activities_of_every_visibility_and_never_the_followees(
        self, db, owner, viewer
    ):
        make_follow(db, owner.id, viewer.id, accepted=True)
        make_activity_at(db, viewer.id, _DAY, visibility=_Visibility.PUBLIC)
        mine = [
            make_activity_at(db, owner.id, _DAY + timedelta(hours=h), visibility=v).id
            for h, v in ((3, _Visibility.PRIVATE), (6, _Visibility.PUBLIC))
        ]

        feed = activity_service.scroll_feed(owner.id, None, 10, db, activity_constants.FeedScope.MINE)

        assert [item.id for item in feed.items] == [mine[1], mine[0]]
        assert set(feed.users) == {owner.id}

    def test_an_empty_feed_has_no_owners_and_no_next_slice(self, db, owner):
        feed = activity_service.scroll_feed(owner.id, None, 10, db)

        assert (feed.items, feed.users, feed.next_cursor) == ([], {}, None)

    def test_a_malformed_cursor_is_refused(self, db, owner):
        with pytest.raises(core_exceptions.InvalidInputError):
            activity_service.scroll_feed(owner.id, "not-a-cursor", 10, db)

    def test_a_hidden_start_still_leaves_a_cursor_for_the_next_slice(self, db, owner):
        for hours in range(3):
            make_activity_at(db, owner.id, _DAY + timedelta(hours=hours), hide_start_time=True)

        first = activity_service.scroll_feed(owner.id, None, 2, db, activity_constants.FeedScope.MINE)
        second = activity_service.scroll_feed(owner.id, first.next_cursor, 2, db, activity_constants.FeedScope.MINE)

        assert len(first.items) == 2 and first.next_cursor
        assert len(second.items) == 1
        assert core_pagination.decode_uuid_cursor(first.next_cursor) is not None


class TestSingleReads:
    def test_the_owner_reads_their_activity_with_the_notes_and_a_thumbnail_url(self, db, owner):
        mine = make_activity(db, owner.id, private_notes="mine")
        activity_crud.set_activity_thumbnail_key(mine.id, f"{mine.id}.webp", db)

        read = activity_service.get_activity(mine.id, owner.id, db)

        assert (read.private_notes, bool(read.map_thumbnail_url)) == ("mine", True)

    def test_a_viewer_reads_a_public_activity_without_the_notes(self, db, owner, viewer):
        public = make_activity(db, owner.id, visibility=_Visibility.PUBLIC, private_notes="mine")

        assert activity_service.get_activity(public.id, viewer.id, db).private_notes is None

    @pytest.mark.parametrize("visibility", [_Visibility.PRIVATE, _Visibility.FOLLOWERS])
    def test_a_viewer_who_may_not_see_the_activity_is_told_it_does_not_exist(self, db, owner, viewer, visibility):
        hidden = make_activity(db, owner.id, visibility=visibility)

        with pytest.raises(core_exceptions.NotFoundError):
            activity_service.get_activity(hidden.id, viewer.id, db)

    def test_a_follower_reads_the_followers_activity_of_an_active_owner_but_not_of_an_inactive_one(self, db, viewer):
        active = make_user(db)
        inactive = make_user(db)
        make_follow(db, viewer.id, active.id, accepted=True)
        make_follow(db, viewer.id, inactive.id, accepted=True)
        readable = make_activity(db, active.id, visibility=_Visibility.FOLLOWERS)
        gone = make_activity(db, inactive.id, visibility=_Visibility.PUBLIC)
        _deactivate(db, inactive)

        assert activity_service.get_activity(readable.id, viewer.id, db).id == readable.id
        with pytest.raises(core_exceptions.NotFoundError):
            activity_service.get_activity(gone.id, viewer.id, db)

    def test_an_activity_that_does_not_exist_is_not_found(self, db, owner):
        with pytest.raises(core_exceptions.NotFoundError):
            activity_service.get_activity(uuid.uuid4(), owner.id, db)

    def test_the_owner_still_reads_their_own_activity_when_inactive(self, db):
        inactive = make_user(db, active=False)
        mine = make_activity(db, inactive.id)

        assert activity_service.get_activity(mine.id, inactive.id, db).id == mine.id


class TestPublicReads:
    def test_a_public_activity_is_readable_only_while_the_server_shares_public_links(self, db, owner):
        public = make_activity(db, owner.id, visibility=_Visibility.PUBLIC, private_notes="mine")

        with pytest.raises(core_exceptions.NotFoundError):
            activity_service.get_public_activity(public.id, db)
        edit_server_settings(db, public_shareable_links=True)

        read = activity_service.get_public_activity(public.id, db)
        assert (read.id, read.private_notes) == (public.id, None)

    @pytest.mark.parametrize(
        "fields",
        [{"visibility": _Visibility.FOLLOWERS}, {"visibility": _Visibility.PRIVATE}, {"is_hidden": True}],
    )
    def test_an_activity_that_is_not_public_is_not_found_by_a_public_link(self, db, owner, fields):
        edit_server_settings(db, public_shareable_links=True)
        activity = make_activity(db, owner.id, **{"visibility": _Visibility.PUBLIC, **fields})

        with pytest.raises(core_exceptions.NotFoundError):
            activity_service.get_public_activity(activity.id, db)

    def test_a_public_link_of_an_inactive_owner_is_not_found(self, db):
        edit_server_settings(db, public_shareable_links=True)
        gone = make_user(db, active=False)
        activity = make_activity(db, gone.id, visibility=_Visibility.PUBLIC)

        with pytest.raises(core_exceptions.NotFoundError):
            activity_service.get_public_activity(activity.id, db)


class TestEdit:
    def _edit(self, db, user, activity, **fields):
        return activity_service.edit_activity(
            activity.id, user.id, activity_schema.ActivityEdit(**fields), db, if_match=f'"{activity.version}"'
        )

    def test_the_edit_is_stored_and_publishes_updated_with_only_the_fields_sent(self, db, owner, published):
        activity = make_activity(db, owner.id)

        edited = self._edit(db, owner, activity, name="Renamed", description="d")

        row = db.get(activity_models.Activity, activity.id)
        assert (row.name, row.description, edited.version) == ("Renamed", "d", activity.version + 1)
        [event] = published[activity_events.ACTIVITY_UPDATED]
        assert event.payload["activity_id"] == str(activity.id)
        assert event.payload["changed_fields"] == ["description", "name"]

    def test_a_stale_edit_changes_nothing_and_publishes_nothing(self, db, owner, published):
        activity = make_activity(db, owner.id, name="Original")

        with pytest.raises(core_exceptions.PreconditionFailedError):
            activity_service.edit_activity(
                activity.id, owner.id, activity_schema.ActivityEdit(name="Late"), db, if_match='"99"'
            )

        assert db.get(activity_models.Activity, activity.id).name == "Original"
        assert published[activity_events.ACTIVITY_UPDATED] == []

    def test_a_gear_the_user_does_not_own_is_refused_before_anything_is_written(self, db, owner, viewer, published):
        theirs = make_gear(db, viewer.id)
        activity = make_activity(db, owner.id, name="Original")

        with pytest.raises(core_exceptions.NotFoundError):
            self._edit(db, owner, activity, name="New", gear_id=theirs.id)

        assert db.get(activity_models.Activity, activity.id).name == "Original"
        assert published[activity_events.ACTIVITY_UPDATED] == []

    def test_an_activity_of_another_user_is_not_found(self, db, owner, viewer):
        theirs = make_activity(db, viewer.id)

        with pytest.raises(core_exceptions.NotFoundError):
            self._edit(db, owner, theirs, name="Mine now")

    def test_a_changed_visibility_and_hide_flag_are_audited_by_name_and_never_by_value(self, db, owner):
        activity = make_activity(db, owner.id)

        self._edit(db, owner, activity, visibility=_Visibility.PUBLIC, hide_hr=True, name="Renamed")

        [row] = audit_rows_of(db, activity_audit_actions.VISIBILITY_UPDATE.id)
        assert (row.target_type, row.target_id, row.target_owner_id) == ("activity", str(activity.id), str(owner.id))
        assert sorted(row.details["changed_fields"]) == ["hide_hr", "visibility"]
        assert "Renamed" not in str(row.details)

    def test_an_edit_that_changes_no_visibility_field_is_not_audited(self, db, owner):
        activity = make_activity(db, owner.id)

        self._edit(db, owner, activity, name="Renamed")

        assert audit_rows_of(db, activity_audit_actions.VISIBILITY_UPDATE.id) == []

    def test_a_visibility_sent_again_unchanged_is_not_audited(self, db, owner):
        activity = make_activity(db, owner.id, visibility=_Visibility.PRIVATE)

        self._edit(db, owner, activity, visibility=_Visibility.PRIVATE)

        assert audit_rows_of(db, activity_audit_actions.VISIBILITY_UPDATE.id) == []


class TestDelete:
    def test_the_activity_goes_and_deleted_is_published(self, db, owner, published):
        activity = make_activity(db, owner.id)

        activity_service.delete_activity(activity.id, owner.id, db, if_match=f'"{activity.version}"')

        assert db.get(activity_models.Activity, activity.id) is None
        [event] = published[activity_events.ACTIVITY_DELETED]
        assert event.payload["activity_id"] == str(activity.id)

    def test_a_stale_delete_keeps_the_activity_and_publishes_nothing(self, db, owner, published):
        activity = make_activity(db, owner.id)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            activity_service.delete_activity(activity.id, owner.id, db, if_match='"99"')

        assert db.get(activity_models.Activity, activity.id) is not None
        assert published[activity_events.ACTIVITY_DELETED] == []

    def test_another_users_activity_is_not_found_and_stays(self, db, owner, viewer):
        theirs = make_activity(db, viewer.id)

        with pytest.raises(core_exceptions.NotFoundError):
            activity_service.delete_activity(theirs.id, owner.id, db, if_match="*")

        assert db.get(activity_models.Activity, theirs.id) is not None

    def test_ownership_is_answered_by_the_owner_only(self, db, owner, viewer):
        mine = make_activity(db, owner.id)

        assert activity_service.owns_activity(mine.id, owner.id, db) is True
        assert activity_service.owns_activity(mine.id, viewer.id, db) is False


class TestWritesFromOtherModules:
    def test_a_bulk_gear_assignment_publishes_one_update_per_changed_activity(self, db, owner, viewer, published):
        gear = make_gear(db, owner.id)
        mine = [make_activity_at(db, owner.id, _DAY + timedelta(days=n)) for n in range(2)]
        theirs = make_activity(db, viewer.id)

        count = activity_service.bulk_set_activities_gear(
            owner.id, {**{a.id: gear.id for a in mine}, theirs.id: gear.id}, db, source="test:gear"
        )
        db.commit()

        assert count == 2
        events = published[activity_events.ACTIVITY_UPDATED]
        assert sorted(e.payload["activity_id"] for e in events) == sorted(str(a.id) for a in mine)
        assert {e.source for e in events} == {"test:gear"}
        assert {tuple(e.payload["changed_fields"]) for e in events} == {("gear_id",)}

    def test_clearing_a_gear_publishes_one_update_per_activity_that_carried_it(self, db, owner, published):
        gear = make_gear(db, owner.id)
        carried = make_activity_at(db, owner.id, _DAY, gear_id=gear.id)
        make_activity_at(db, owner.id, _DAY + timedelta(days=1))

        assert activity_service.clear_activities_gear(gear.id, owner.id, 10, db, source="test:gear") == 1
        db.commit()

        assert [e.payload["activity_id"] for e in published[activity_events.ACTIVITY_UPDATED]] == [str(carried.id)]

    def test_deleting_strava_activities_publishes_the_cleanup_event_for_each(self, db, owner, published):
        synced = make_activity_at(db, owner.id, _DAY, strava_activity_id=1)
        make_activity_at(db, owner.id, _DAY + timedelta(days=1))

        assert activity_service.delete_all_strava_activities(owner.id, db, source="test:strava", limit=10) == 1
        db.commit()

        [event] = published[activity_events.ACTIVITY_DELETED]
        assert (event.payload["activity_id"], event.source) == (str(synced.id), "test:strava")

    def test_deleting_a_users_activities_in_batches_publishes_the_cleanup_event_for_each(self, db, owner, published):
        ids = {str(make_activity_at(db, owner.id, _DAY + timedelta(days=n)).id) for n in range(3)}

        deleted = activity_service.delete_activities_batch_for_user(owner.id, 2, db, source="test:account")
        deleted += activity_service.delete_activities_batch_for_user(owner.id, 2, db, source="test:account")
        db.commit()

        assert deleted == 3
        assert {e.payload["activity_id"] for e in published[activity_events.ACTIVITY_DELETED]} == ids

    def test_the_tombstones_past_the_retention_are_pruned_and_counted(self, db, owner):
        activity = make_activity(db, owner.id)
        activity_service.delete_activity(activity.id, owner.id, db, if_match="*")

        assert activity_service.prune_activity_deletions(datetime.now(UTC), db) == 0
        assert activity_service.prune_activity_deletions(datetime.now(UTC) + timedelta(days=3650), db) == 1
