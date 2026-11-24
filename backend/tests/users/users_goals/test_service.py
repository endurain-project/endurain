"""The goals service: pages, commits and refusals, on the real database."""

import uuid

import pytest

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.users.users_goals.schema as schema
import modules.users.users_goals.service as service
from tests._factories.goals import make_goal
from tests._factories.users import make_user

_NEW_GOAL = schema.UserGoalCreate(interval="daily", activity_type="bike", goal_type="duration", goal_duration=3600)


@pytest.fixture
def owner(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created


def test_a_page_carries_the_total_of_the_filtered_goals(db, user):
    make_goal(db, user.id, interval="daily")
    make_goal(db, user.id, interval="weekly")
    make_goal(db, user.id, interval="monthly")

    page = service.list_goals(user.id, core_pagination.PageParams(2, 2), db)
    weekly = service.list_goals(user.id, core_pagination.PageParams(1, 25), db, interval=schema.Interval.WEEKLY)

    assert (page.total, page.page, page.num_records, page.next, len(page.items)) == (3, 2, 2, None, 1)
    assert (weekly.total, [g.interval for g in weekly.items]) == (1, ["weekly"])


def test_a_created_goal_survives_in_a_new_session(committed_sessions, owner):
    with committed_sessions() as db:
        created = service.create_goal(owner.id, _NEW_GOAL, db)

    with committed_sessions() as db:
        assert service.get_goal(owner.id, created.id, db) == created


def test_a_duplicate_goal_is_a_conflict_and_the_first_one_stays(committed_sessions, owner):
    with committed_sessions() as db:
        service.create_goal(owner.id, _NEW_GOAL, db)

    with committed_sessions() as db, pytest.raises(core_exceptions.ConflictError):
        service.create_goal(owner.id, _NEW_GOAL, db)

    with committed_sessions() as db:
        assert service.list_goals(owner.id, core_pagination.PageParams(1, 25), db).total == 1


def test_an_update_commits_the_replacement(committed_sessions, owner):
    with committed_sessions() as db:
        created = service.create_goal(owner.id, _NEW_GOAL, db)
    change = schema.UserGoalUpdate(interval="daily", activity_type="bike", goal_type="duration", goal_duration=7200)

    with committed_sessions() as db:
        service.update_goal(owner.id, created.id, change, db, if_match='"1"')

    with committed_sessions() as db:
        stored = service.get_goal(owner.id, created.id, db)
    assert (stored.goal_duration, stored.version) == (7200, 2)


class TestRefusals:
    def test_a_stale_update_is_a_precondition_failure(self, db, user):
        goal = make_goal(db, user.id)
        change = schema.UserGoalUpdate(interval="weekly", activity_type="run", goal_type="distance", goal_distance=1)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            service.update_goal(user.id, goal.id, change, db, if_match='"4"')

    def test_updating_a_missing_goal_is_not_found(self, db, user):
        change = schema.UserGoalUpdate(interval="weekly", activity_type="run", goal_type="distance", goal_distance=1)

        with pytest.raises(core_exceptions.NotFoundError):
            service.update_goal(user.id, uuid.uuid4(), change, db, if_match="*")

    def test_a_stale_delete_keeps_the_goal(self, db, user):
        goal = make_goal(db, user.id)

        with pytest.raises(core_exceptions.PreconditionFailedError):
            service.delete_goal(user.id, goal.id, db, if_match='"4"')

        assert service.get_goal(user.id, goal.id, db) == goal

    def test_deleting_a_missing_goal_is_not_found(self, db, user):
        with pytest.raises(core_exceptions.NotFoundError):
            service.delete_goal(user.id, uuid.uuid4(), db, if_match="*")

    def test_a_delete_removes_the_goal(self, db, user):
        goal = make_goal(db, user.id)

        service.delete_goal(user.id, goal.id, db, if_match='"1"')

        with pytest.raises(core_exceptions.NotFoundError):
            service.get_goal(user.id, goal.id, db)
