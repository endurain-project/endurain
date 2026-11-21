"""Goal progress against real activities: windows, sports, hidden duplicates and the user's own day."""

import uuid
from datetime import UTC, date, datetime, timedelta

import jasil.runtime as jasil_runtime
import pytest

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.activities.activity.constants as activity_constants
import modules.users.users_goals.crud as goals_crud
import modules.users.users_goals.progress_service as progress_service
import modules.users.users_goals.schema as goals_schema
from tests._factories.activities import make_activity
from tests._factories.goals import make_goal
from tests._factories.users import make_user

_PAGE = core_pagination.PageParams(1, 25)
_RUN = activity_constants.ActivityType.RUN.stored
_RIDE = activity_constants.ActivityType.RIDE.stored
# Wednesday 2025-03-12 noon UTC; the week runs Monday 10th to Sunday 16th.
_WEDNESDAY = datetime(2025, 3, 12, 12, 0, tzinfo=UTC)


def _at(day: int, hour: int = 8) -> datetime:
    return datetime(2025, 3, day, hour, 0, tzinfo=UTC)


def _progress(db, user, goal, on="2025-03-12", first_day="monday"):
    return progress_service.calculate_goal_progress_by_activity_type(goal, on, first_day, db)


@pytest.fixture(autouse=True)
def clock():
    platform_clock = jasil_runtime.get_active_platform().clock
    platform_clock.moment = _WEDNESDAY
    return platform_clock


class TestGoalMetrics:
    def test_a_distance_goal_adds_up_the_distance_in_the_window(self, db, user):
        goal = make_goal(db, user.id, goal_distance=40000)
        make_activity(db, user.id, start_time=_at(10), distance=10000)
        make_activity(db, user.id, start_time=_at(12), distance=10000)
        make_activity(db, user.id, start_time=_at(9), distance=99999)

        progress = _progress(db, user, goal)

        assert (progress.start_date, progress.end_date) == (date(2025, 3, 10), date(2025, 3, 16))
        assert (progress.total_distance, progress.percentage_completed, progress.goal_distance) == (20000, 50, 40000)

    def test_a_calories_goal_adds_up_the_calories(self, db, user):
        goal = make_goal(db, user.id, goal_type="calories", goal_calories=1000, goal_distance=None)
        make_activity(db, user.id, start_time=_at(11), calories=300)
        make_activity(db, user.id, start_time=_at(13), calories=450)

        progress = _progress(db, user, goal)

        assert (progress.total_calories, progress.percentage_completed) == (750, 75)

    def test_an_activities_goal_counts_the_activities(self, db, user):
        goal = make_goal(db, user.id, goal_type="activities", goal_activities_number=4, goal_distance=None)
        for day in (10, 11, 12):
            make_activity(db, user.id, start_time=_at(day))

        progress = _progress(db, user, goal)

        assert (progress.total_activities_number, progress.percentage_completed) == (3, 75)

    def test_an_elevation_goal_adds_up_the_elevation_gain(self, db, user):
        goal = make_goal(db, user.id, goal_type="elevation", goal_elevation=1000, goal_distance=None)
        make_activity(db, user.id, start_time=_at(10), elevation_gain=250)
        make_activity(db, user.id, start_time=_at(11), elevation_gain=250)

        progress = _progress(db, user, goal)

        assert (progress.total_elevation, progress.percentage_completed) == (500, 50)

    def test_a_duration_goal_adds_up_the_elapsed_time(self, db, user):
        goal = make_goal(db, user.id, goal_type="duration", goal_duration=14400, goal_distance=None)
        make_activity(db, user.id, start_time=_at(10), total_elapsed_time=3600)
        make_activity(db, user.id, start_time=_at(11), total_elapsed_time=3600)

        progress = _progress(db, user, goal)

        assert (progress.total_duration, progress.percentage_completed) == (7200, 50)

    def test_completion_is_capped_at_one_hundred_percent(self, db, user):
        goal = make_goal(db, user.id, goal_distance=5000)
        make_activity(db, user.id, start_time=_at(10), distance=20000)

        progress = _progress(db, user, goal)

        assert (progress.total_distance, progress.percentage_completed) == (20000, 100)

    def test_no_activity_in_the_window_is_zero_progress(self, db, user):
        goal = make_goal(db, user.id)
        make_activity(db, user.id, start_time=_at(2))

        progress = _progress(db, user, goal)

        assert (progress.total_distance, progress.percentage_completed) == (0, 0)


class TestWhatCounts:
    def test_hidden_activities_do_not_count_twice(self, db, user):
        goal = make_goal(db, user.id, goal_type="activities", goal_activities_number=2, goal_distance=None)
        make_activity(db, user.id, start_time=_at(10))
        make_activity(db, user.id, start_time=_at(10), is_hidden=True)

        assert _progress(db, user, goal).total_activities_number == 1

    def test_only_the_goals_sport_counts(self, db, user):
        goal = make_goal(db, user.id, activity_type="bike", goal_distance=100000)
        make_activity(db, user.id, start_time=_at(10), activity_type=_RUN, distance=7000)
        make_activity(db, user.id, start_time=_at(11), activity_type=_RIDE, distance=30000)

        assert _progress(db, user, goal).total_distance == 30000

    def test_a_walking_goal_also_counts_hikes(self, db, user):
        goal = make_goal(db, user.id, activity_type="walk", goal_distance=10000)
        make_activity(
            db, user.id, start_time=_at(10), activity_type=activity_constants.ActivityType.WALK.stored, distance=2000
        )
        make_activity(
            db, user.id, start_time=_at(11), activity_type=activity_constants.ActivityType.HIKE.stored, distance=3000
        )

        assert _progress(db, user, goal).total_distance == 5000

    def test_a_cardio_goal_counts_its_own_types(self, db, user):
        goal = make_goal(
            db, user.id, activity_type="cardio", goal_type="activities", goal_activities_number=2, goal_distance=None
        )
        make_activity(db, user.id, start_time=_at(10), activity_type=activity_constants.ActivityType.JUMP_ROPE.stored)
        make_activity(db, user.id, start_time=_at(11), activity_type=_RUN)

        assert _progress(db, user, goal).total_activities_number == 1

    def test_a_strength_goal_counts_the_default_types(self, db, user):
        goal = make_goal(
            db, user.id, activity_type="strength", goal_type="activities", goal_activities_number=1, goal_distance=None
        )
        make_activity(db, user.id, start_time=_at(10), activity_type=10)
        make_activity(db, user.id, start_time=_at(11), activity_type=_RUN)

        assert _progress(db, user, goal).total_activities_number == 1

    def test_another_users_activities_do_not_count(self, db, user, other):
        goal = make_goal(db, user.id)
        make_activity(db, other.id, start_time=_at(10), distance=9000)

        assert _progress(db, user, goal).total_distance == 0


class TestWindows:
    @pytest.mark.parametrize(
        ("interval", "start", "end"),
        [
            ("daily", date(2025, 3, 12), date(2025, 3, 12)),
            ("weekly", date(2025, 3, 10), date(2025, 3, 16)),
            ("monthly", date(2025, 3, 1), date(2025, 3, 31)),
            ("yearly", date(2025, 1, 1), date(2025, 12, 31)),
        ],
    )
    def test_each_interval_spans_the_period_around_the_date(self, db, user, interval, start, end):
        goal = make_goal(db, user.id, interval=interval)

        progress = _progress(db, user, goal)

        assert (progress.start_date, progress.end_date) == (start, end)

    def test_the_week_starts_on_the_users_first_day(self, db, user):
        goal = make_goal(db, user.id)

        progress = _progress(db, user, goal, first_day="sunday")

        assert (progress.start_date, progress.end_date) == (date(2025, 3, 9), date(2025, 3, 15))


class TestCalculateUserGoals:
    def test_a_page_of_goals_is_evaluated_with_the_total(self, db, user):
        now = datetime.now(UTC)
        for interval, age in (("daily", 3), ("weekly", 2), ("monthly", 1)):
            goal = goals_schema.UserGoalCreate(
                interval=interval, activity_type="run", goal_type="distance", goal_distance=50000
            )
            goals_crud.create_user_goal(user.id, goal, db, created_at=now - timedelta(hours=age))
        make_activity(db, user.id, start_time=_at(12), distance=25000)

        page = progress_service.calculate_user_goals(
            user.id, "2025-03-12", "monday", core_pagination.PageParams(1, 2), db
        )

        assert (page.total, page.next, len(page.items)) == (3, 2, 2)
        assert [item.interval for item in page.items] == ["daily", "weekly"]
        assert [item.percentage_completed for item in page.items] == [50, 50]

    def test_no_goals_is_an_empty_page(self, db, user):
        page = progress_service.calculate_user_goals(user.id, "2025-03-12", "monday", _PAGE, db)

        assert (page.items, page.total) == ([], 0)

    def test_without_a_date_the_users_own_day_is_used(self, db, clock):
        # 23:30 UTC on the 12th is already the 13th in Tokyo.
        clock.moment = datetime(2025, 3, 12, 23, 30, tzinfo=UTC)
        tokyo = make_user(db, timezone="Asia/Tokyo", first_day_of_week="monday")
        make_goal(db, tokyo.id, interval="daily")

        page = progress_service.calculate_user_goals(tokyo.id, None, "monday", _PAGE, db)

        assert page.items[0].start_date == date(2025, 3, 13)

    def test_an_unknown_interval_is_invalid_input(self, db, user):
        goal = make_goal(db, user.id)
        broken = goal.model_copy(update={"interval": "hourly"})

        with pytest.raises(core_exceptions.InvalidInputError):
            progress_service.calculate_goal_progress_by_activity_type(broken, "2025-03-12", "monday", db)


class TestGetGoalsProgress:
    def test_progress_is_anchored_on_the_users_own_day(self, db, clock):
        clock.moment = datetime(2025, 3, 12, 23, 30, tzinfo=UTC)
        tokyo = make_user(db, timezone="Asia/Tokyo", first_day_of_week="sunday")
        make_goal(db, tokyo.id, interval="weekly")

        page = progress_service.get_goals_progress(tokyo.id, _PAGE, db)

        # Thursday the 13th in Tokyo; the week starts on Sunday the 9th.
        assert (page.items[0].start_date, page.items[0].end_date) == (date(2025, 3, 9), date(2025, 3, 15))

    def test_an_unknown_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            progress_service.get_goals_progress(uuid.uuid4(), _PAGE, db)
