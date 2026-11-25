"""What a multisport activity and its legs add to the reads: lists, counts, feeds, sums and summaries, on PostgreSQL."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import update

import modules.activities.activity.constants as activity_constants
import modules.activities.activity.crud as activity_crud
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
import modules.activities.activity.service as activity_service
import modules.activities.activity.summary_crud as summary_crud
import modules.gears.contracts as gears_contracts
from tests._factories.activities import make_activity_at, make_multisport
from tests._factories.followers import make_follow
from tests._factories.gears import make_gear
from tests._factories.users import make_user

_Visibility = activity_constants.ActivityVisibility
_Type = activity_constants.ActivityType
_START = datetime(2026, 7, 28, 9, tzinfo=UTC)
_WINDOW = (datetime(2026, 7, 27, tzinfo=UTC), datetime(2026, 8, 2, tzinfo=UTC))
_LEG_DISTANCE = 1500 + 40000 + 10000
_LEG_SECONDS = (30 + 5 + 60 + 3 + 45) * 60.0


@pytest.fixture
def owner(db):
    return make_user(db, timezone="UTC")


@pytest.fixture
def viewer(db):
    return make_user(db, timezone="UTC")


def _page(db, owner, requester, **filters):
    return activity_service.page_user_activities(owner.id, requester.id, db, page_number=1, num_records=50, **filters)


class TestTopLevelReaders:
    def test_the_owners_page_and_total_hold_the_parent_and_not_its_legs(self, db, owner):
        parent, _ = make_multisport(db, owner.id)
        alone = make_activity_at(db, owner.id, _START + timedelta(days=1))

        page = _page(db, owner, owner)

        assert {item.id for item in page.items} == {parent.id, alone.id}
        assert page.total == 2

    def test_another_users_page_and_total_hold_the_visible_parent_and_not_its_legs(self, db, owner, viewer):
        parent, _ = make_multisport(db, owner.id, visibility=_Visibility.PUBLIC)

        page = _page(db, owner, viewer)

        assert [item.id for item in page.items] == [parent.id]
        assert page.total == 1

    def test_the_count_the_profile_overview_shows_counts_a_triathlon_once(self, db, owner):
        make_multisport(db, owner.id, start=_START)

        assert activity_service.count_user_activities(owner.id, db) == 1
        month = activity_service.user_profile_summary(owner.id, owner.id, db, anchor=date(2026, 7, 28))
        assert month.month_activity_count == 1

    def test_filtering_by_a_leg_type_finds_no_leg_and_filtering_by_multisport_finds_the_parent(self, db, owner):
        parent, _ = make_multisport(db, owner.id)

        assert _page(db, owner, owner, activity_type=_Type.RUN).items == []
        assert [item.id for item in _page(db, owner, owner, activity_type=_Type.MULTISPORT).items] == [parent.id]

    def test_a_name_search_finds_the_parent_and_never_a_leg(self, db, owner):
        parent, _ = make_multisport(db, owner.id, legs=[{"activity_type": 1, "distance": 5000, "minutes": 30}])
        make_activity_at(db, owner.id, _START + timedelta(days=1), name="Morning run")

        assert [item.id for item in _page(db, owner, owner, name_search="Triathlon").items] == [parent.id]
        assert [item.name for item in _page(db, owner, owner, name_search="Morning").items] == ["Morning run"]

    def test_filtering_by_gear_lists_the_legs_ridden_on_it(self, db, owner):
        gear = make_gear(db, owner.id)
        _, legs = make_multisport(
            db,
            owner.id,
            legs=[
                {"activity_type": _Type.OPEN_WATER_SWIMMING.stored, "distance": 1500, "minutes": 30},
                {"activity_type": _Type.RIDE.stored, "distance": 40000, "minutes": 60, "gear_id": gear.id},
            ],
        )

        page = _page(db, owner, owner, gear_id=gear.id)

        assert [item.id for item in page.items] == [legs[1].id]
        assert page.total == 1

    def test_the_activity_types_listed_are_the_ones_of_top_level_activities(self, db, owner):
        make_multisport(db, owner.id)
        make_activity_at(db, owner.id, _START + timedelta(days=1), activity_type=_Type.WALK.stored)

        assert list(activity_service.list_activity_types(owner.id, db)) == [_Type.WALK, _Type.MULTISPORT]

    def test_the_following_feed_lists_the_parent_and_not_its_legs(self, db, owner, viewer):
        make_follow(db, viewer.id, owner.id, accepted=True)
        parent, _ = make_multisport(db, owner.id, visibility=_Visibility.PUBLIC)

        feed = activity_service.scroll_feed(viewer.id, None, 20, db)

        assert [item.id for item in feed.items] == [parent.id]

    def test_the_own_feed_lists_the_parent_and_not_its_legs(self, db, owner):
        parent, _ = make_multisport(db, owner.id)

        feed = activity_service.scroll_feed(owner.id, None, 20, db, activity_constants.FeedScope.MINE)

        assert [item.id for item in feed.items] == [parent.id]

    def test_a_leg_is_still_read_by_its_id_and_names_its_parent(self, db, owner):
        parent, legs = make_multisport(db, owner.id)

        read = activity_service.get_activity(legs[2].id, owner.id, db)

        assert read.parent_activity_id == parent.id
        assert activity_service.get_activity(parent.id, owner.id, db).parent_activity_id is None

    def test_a_leg_of_a_public_parent_is_read_under_its_own_visibility(self, db, owner, viewer):
        _, legs = make_multisport(db, owner.id, visibility=_Visibility.PUBLIC)

        assert activity_service.get_activity(legs[0].id, viewer.id, db).id == legs[0].id

    def test_a_walk_over_the_whole_library_holds_the_legs_too(self, db, owner):
        parent, legs = make_multisport(db, owner.id)

        walked = activity_integration.list_user_activities_page(owner.id, db, page_number=1, num_records=50)

        assert {activity.id for activity in walked} == {parent.id, *(leg.id for leg in legs)}


class TestSums:
    def test_the_stats_add_up_the_legs_by_type_and_leave_the_parent_out(self, db, owner):
        make_multisport(db, owner.id, start=_START)

        totals = {
            total.activity_type: total
            for total in activity_crud.sum_user_activities_per_timeframe_by_type(
                *(owner.id, *_WINDOW), db, user_is_owner=True
            )
        }

        assert set(totals) == {
            _Type.OPEN_WATER_SWIMMING.stored,
            _Type.TRANSITION.stored,
            _Type.RIDE.stored,
            _Type.RUN.stored,
        }
        assert totals[_Type.RIDE.stored].distance == 40000.0
        assert sum(total.distance for total in totals.values()) == _LEG_DISTANCE
        assert sum(total.time for total in totals.values()) == _LEG_SECONDS

    def test_the_stats_of_another_user_add_up_the_legs_of_a_visible_triathlon(self, db, owner, viewer):
        make_follow(db, viewer.id, owner.id, accepted=True)
        make_multisport(db, owner.id, start=_START, visibility=_Visibility.FOLLOWERS)

        totals = activity_service.sum_activities_in_timeframe(owner.id, *_WINDOW, viewer.id, db)

        assert sum(total.distance for total in totals) == _LEG_DISTANCE

    def test_a_goal_counts_a_run_leg_as_a_run_and_the_parent_toward_no_sport(self, db, owner):
        make_multisport(
            db,
            owner.id,
            start=_START,
            legs=[
                {
                    "activity_type": _Type.RUN.stored,
                    "distance": 10000,
                    "minutes": 45,
                    "calories": 600,
                    "elevation_gain": 80,
                },
            ],
        )

        runs = activity_crud.sum_user_activities_per_timeframe_and_activity_types(
            owner.id, [*activity_constants.ACTIVITY_TYPES_BY_SPORT["run"]], *_WINDOW, db
        )
        everything = activity_crud.sum_user_activities_per_timeframe_and_activity_types(
            owner.id, [int(_Type.MULTISPORT.stored)], *_WINDOW, db
        )

        assert (runs.count, runs.distance, runs.calories, runs.elevation_gain) == (1, 10000.0, 600.0, 80.0)
        assert runs.elapsed_time == 45 * 60.0
        assert (everything.count, everything.distance) == (0, 0.0)

    def test_gear_usage_adds_up_the_legs_ridden_on_the_gear_and_never_the_parent(self, db, owner):
        gear = make_gear(db, owner.id)
        parent, _ = make_multisport(
            db,
            owner.id,
            start=_START,
            legs=[{"activity_type": _Type.RIDE.stored, "distance": 40000, "minutes": 60, "gear_id": gear.id}],
        )
        db.execute(
            update(activity_models.Activity).where(activity_models.Activity.id == parent.id).values(gear_id=gear.id)
        )
        db.flush()

        usage = activity_crud.sum_gear_usage([gear.id], owner.id, db)
        by_window = activity_crud.sum_gear_usage_by_window(
            gear.id,
            owner.id,
            [gears_contracts.UsageWindow(key=gear.id, start_date=date(2026, 7, 1), end_date=None)],
            db,
        )

        assert (usage[gear.id].distance, usage[gear.id].time) == (40000.0, 3600.0)
        assert (by_window[gear.id].distance, by_window[gear.id].time) == (40000.0, 3600.0)


class TestSummaries:
    @pytest.fixture
    def group(self, db, owner):
        make_multisport(
            db,
            owner.id,
            start=_START,
            legs=[
                {
                    "activity_type": _Type.RIDE.stored,
                    "distance": 40000,
                    "minutes": 60,
                    "calories": 900,
                    "elevation_gain": 300,
                },
                {
                    "activity_type": _Type.RUN.stored,
                    "distance": 10000,
                    "minutes": 45,
                    "calories": 600,
                    "elevation_gain": 80,
                },
            ],
        )
        make_activity_at(db, owner.id, _START + timedelta(days=1), distance=5000, calories=300, elevation_gain=20)
        return owner.id

    @pytest.mark.parametrize(
        "summarize",
        [
            lambda db, user_id, **kw: summary_crud.get_weekly_summary(user_id, date(2026, 7, 29), "monday", db, **kw),
            lambda db, user_id, **kw: summary_crud.get_monthly_summary(user_id, date(2026, 7, 29), "monday", db, **kw),
            lambda db, user_id, **kw: summary_crud.get_yearly_summary(user_id, 2026, db, **kw),
            lambda db, user_id, **kw: summary_crud.get_lifetime_summary(user_id, db, **kw),
        ],
        ids=["weekly", "monthly", "yearly", "lifetime"],
    )
    def test_the_totals_add_up_the_legs_once_and_a_triathlon_counts_once(self, db, group, summarize):
        summary = summarize(db, group)

        assert summary.total_distance == 55000.0
        assert summary.total_duration == (60 + 45) * 60.0 + 3600.0
        assert summary.total_elevation_gain == 400.0
        assert summary.total_calories == 1800.0
        assert summary.activity_count == 2

    @pytest.mark.parametrize(
        "summarize",
        [
            lambda db, user_id, **kw: summary_crud.get_weekly_summary(user_id, date(2026, 7, 29), "monday", db, **kw),
            lambda db, user_id, **kw: summary_crud.get_monthly_summary(user_id, date(2026, 7, 29), "monday", db, **kw),
            lambda db, user_id, **kw: summary_crud.get_yearly_summary(user_id, 2026, db, **kw),
            lambda db, user_id, **kw: summary_crud.get_lifetime_summary(user_id, db, **kw),
        ],
        ids=["weekly", "monthly", "yearly", "lifetime"],
    )
    def test_the_breakdown_by_type_counts_a_leg_as_its_sport_and_has_no_multisport_entry(self, db, group, summarize):
        summary = summarize(db, group)

        breakdown = {item.activity_type: item for item in summary.type_breakdown}
        assert set(breakdown) == {_Type.RIDE, _Type.RUN}
        assert (breakdown[_Type.RUN].activity_count, breakdown[_Type.RUN].total_distance) == (2, 15000.0)

    def test_a_summary_of_one_type_counts_that_types_activities_legs_included(self, db, group):
        summary = summary_crud.get_weekly_summary(group, date(2026, 7, 29), "monday", db, activity_type=_Type.RUN)

        assert (summary.activity_count, summary.total_distance) == (2, 15000.0)


class TestSync:
    def test_a_changed_leg_comes_with_its_parent(self, db, owner):
        parent, legs = make_multisport(db, owner.id, start=_START)

        changed = activity_service.list_changed_activities(
            owner.id, None, datetime.now(UTC) + timedelta(minutes=1), 50, db
        )

        by_id = {activity.id: activity.parent_activity_id for activity in changed}
        assert by_id == {parent.id: None, **{leg.id: parent.id for leg in legs}}
