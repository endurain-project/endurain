"""Goals against the real database: filtered pages, the one-goal-per-slot rule, replacement and deletion."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

import core.exceptions as core_exceptions
import modules.users.users.models as users_models
import modules.users.users_goals.crud as crud
import modules.users.users_goals.models as goals_models
import modules.users.users_goals.schema as schema
from tests._factories.goals import make_goal


class TestListing:
    def test_the_filters_narrow_the_goals_and_the_count_agrees(self, db, user, other):
        make_goal(db, user.id, interval="weekly", activity_type="run")
        make_goal(db, user.id, interval="monthly", activity_type="run")
        make_goal(db, user.id, interval="weekly", activity_type="bike")
        make_goal(
            db,
            user.id,
            interval="weekly",
            activity_type="swim",
            goal_type="calories",
            goal_calories=500,
            goal_distance=None,
        )
        make_goal(db, other.id)

        everything = crud.get_user_goals_by_user_id(user.id, db)
        weekly_runs = crud.get_user_goals_by_user_id(
            user.id, db, schema.Interval.WEEKLY, schema.GoalActivityType.RUN, schema.GoalType.DISTANCE
        )

        assert len(everything) == 4
        assert [(g.interval, g.activity_type) for g in weekly_runs] == [("weekly", "run")]
        assert crud.count_user_goals(user.id, db) == 4
        assert crud.count_user_goals(user.id, db, interval=schema.Interval.WEEKLY) == 3
        assert crud.count_user_goals(user.id, db, goal_type=schema.GoalType.CALORIES) == 1
        assert crud.count_user_goals(user.id, db, activity_type=schema.GoalActivityType.BIKE) == 1

    def test_a_page_is_one_window_in_creation_order(self, db, user):
        now = datetime.now(UTC)
        # Created in the reverse of their creation times: the order follows the creation time, not the insert order.
        for interval, age in (("monthly", 1), ("weekly", 2), ("daily", 3)):
            goal = schema.UserGoalCreate(
                interval=interval, activity_type="run", goal_type="activities", goal_activities_number=1
            )
            crud.create_user_goal(user.id, goal, db, created_at=now - timedelta(hours=age))

        first = crud.get_user_goals_page(user.id, db, limit=2, offset=0)
        second = crud.get_user_goals_page(user.id, db, limit=2, offset=2)

        assert [g.interval for g in first] == ["daily", "weekly"]
        assert [g.interval for g in second] == ["monthly"]

    def test_a_user_with_no_goals_has_an_empty_page(self, db, user):
        assert crud.get_user_goals_page(user.id, db, limit=10, offset=0) == []
        assert crud.count_user_goals(user.id, db) == 0


class TestCreate:
    def test_the_goal_is_stored_with_its_target_and_a_creation_time(self, db, user):
        created = make_goal(db, user.id, goal_distance=12345)

        stored = crud.get_user_goal(user.id, created.id, db)

        assert stored == created
        assert (stored.goal_distance, stored.goal_calories, stored.version) == (12345, None, 1)

    def test_an_explicit_creation_time_is_kept(self, db, user):
        moment = datetime(2024, 1, 2, 3, 4, tzinfo=UTC)
        goal = crud.create_user_goal(
            user.id,
            schema.UserGoalCreate(
                interval="daily", activity_type="run", goal_type="activities", goal_activities_number=1
            ),
            db,
            created_at=moment,
        )

        row = db.get(goals_models.UsersGoal, goal.id)
        assert row is not None
        assert row.created_at == moment

    def test_the_same_slot_twice_is_a_conflict(self, db, user):
        make_goal(db, user.id)

        with pytest.raises(core_exceptions.ConflictError):
            make_goal(db, user.id, goal_distance=1)

    def test_another_users_identical_goal_is_allowed(self, db, user, other):
        make_goal(db, user.id)

        assert make_goal(db, other.id).user_id == other.id

    def test_deleting_the_user_deletes_the_goals(self, db, user):
        goal = make_goal(db, user.id)

        db.execute(delete(users_models.Users).where(users_models.Users.id == user.id))

        assert crud.user_goal_exists(user.id, goal.id, db) is False


class TestRead:
    def test_another_users_goal_is_not_found(self, db, user, other):
        goal = make_goal(db, other.id)

        with pytest.raises(core_exceptions.NotFoundError):
            crud.get_user_goal(user.id, goal.id, db)

    def test_existence_is_per_owner(self, db, user, other):
        goal = make_goal(db, user.id)

        assert crud.user_goal_exists(user.id, goal.id, db) is True
        assert crud.user_goal_exists(other.id, goal.id, db) is False
        assert crud.user_goal_exists(user.id, uuid.uuid4(), db) is False


class TestUpdate:
    def test_the_goal_is_replaced_and_the_targets_it_leaves_out_are_cleared(self, db, user):
        created = make_goal(db, user.id, goal_distance=10000)
        # As a client sends it: the distance target is simply absent from the body.
        replacement = schema.UserGoalUpdate(
            interval="weekly", activity_type="run", goal_type="calories", goal_calories=5000
        )

        result = crud.update_user_goal(user.id, created.id, replacement, db, if_match='"1"')

        assert (result.goal_calories, result.goal_distance, result.goal_type) == (5000, None, "calories")
        assert result.version == 2

    def test_editing_a_goal_into_another_one_is_a_conflict(self, db, user):
        make_goal(db, user.id)
        monthly = make_goal(db, user.id, interval="monthly")
        into_weekly = schema.UserGoalUpdate(
            interval="weekly", activity_type="run", goal_type="distance", goal_distance=1
        )

        with pytest.raises(core_exceptions.ConflictError):
            crud.update_user_goal(user.id, monthly.id, into_weekly, db, if_match="*")

    def test_a_missing_goal_is_not_found(self, db, user):
        change = schema.UserGoalUpdate(interval="weekly", activity_type="run", goal_type="distance", goal_distance=1)

        with pytest.raises(core_exceptions.NotFoundError):
            crud.update_user_goal(user.id, uuid.uuid4(), change, db, if_match="*")

    def test_a_stale_version_is_refused_and_the_goal_is_unchanged(self, db, user):
        created = make_goal(db, user.id)
        change = schema.UserGoalUpdate(interval="weekly", activity_type="run", goal_type="distance", goal_distance=1)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            crud.update_user_goal(user.id, created.id, change, db, if_match='"3"')

        assert crud.get_user_goal(user.id, created.id, db).goal_distance == 50000


class TestDelete:
    def test_the_goal_is_removed(self, db, user):
        goal = make_goal(db, user.id)

        crud.delete_user_goal(user.id, goal.id, db, if_match='"1"')

        assert crud.user_goal_exists(user.id, goal.id, db) is False

    def test_a_stale_version_is_refused_and_the_goal_stays(self, db, user):
        goal = make_goal(db, user.id)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            crud.delete_user_goal(user.id, goal.id, db, if_match='"2"')

        assert crud.user_goal_exists(user.id, goal.id, db) is True

    def test_a_missing_goal_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError):
            crud.delete_user_goal(user.id, uuid.uuid4(), db, if_match="*")
