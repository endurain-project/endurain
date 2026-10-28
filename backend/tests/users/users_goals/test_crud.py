"""Tests for users.users_goals.crud module."""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import sessionmaker

import core.exceptions as core_exceptions
import modules.users.users_goals.crud as user_goals_crud
import modules.users.users_goals.models as user_goals_models
import modules.users.users_goals.schema as user_goals_schema
from tests._helpers.db import create_sqlite_session, ensure_user


@pytest.fixture(autouse=True)
def _patch_serializer():
    """Patch the serializer to a passthrough for MagicMock compatibility."""
    with patch(
        "modules.users.users_goals.crud.user_goals_serializers.to_read_schema",
        side_effect=lambda x: x,
    ):
        yield


def _one(mock_db, row):
    """Make the session's single-row SELECT return ``row`` (or None)."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = row
    mock_result.first.return_value = row
    mock_db.execute.return_value = mock_result


def _create_input():
    return user_goals_schema.UsersGoalCreate(
        interval="weekly", activity_type="run", goal_type="calories", goal_calories=5000
    )


class TestGetUserGoalsByUserId:
    def test_returns_the_goals(self, mock_db):
        goals = [MagicMock(spec=user_goals_models.UsersGoal), MagicMock(spec=user_goals_models.UsersGoal)]
        mock_db.execute.return_value.scalars.return_value.all.return_value = goals

        assert user_goals_crud.get_user_goals_by_user_id(1, mock_db) == goals

    def test_applies_every_filter(self, mock_db):
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        result = user_goals_crud.get_user_goals_by_user_id(
            1,
            mock_db,
            interval=user_goals_schema.Interval.WEEKLY,
            activity_type=user_goals_schema.ActivityType.RUN,
            goal_type=user_goals_schema.GoalType.CALORIES,
        )

        assert result == []
        compiled = str(mock_db.execute.call_args.args[0])
        assert "interval" in compiled and "activity_type" in compiled and "goal_type" in compiled


class TestCreateUserGoal:
    def test_stages_without_committing(self, mock_db):
        _one(mock_db, None)

        result = user_goals_crud.create_user_goal(1, _create_input(), mock_db)

        assert isinstance(result, user_goals_models.UsersGoal)
        assert result.user_id == 1
        assert result.goal_calories == 5000
        mock_db.add.assert_called_once_with(result)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()


class TestUpdateUserGoal:
    def test_applies_the_set_fields_and_stages(self, mock_db):
        row = MagicMock(spec=user_goals_models.UsersGoal)
        row.version = 1
        _one(mock_db, row)
        update = user_goals_schema.UsersGoalUpdate(
            interval="weekly", activity_type="run", goal_type="calories", goal_calories=9000
        )

        result = user_goals_crud.update_user_goal(1, 7, update, mock_db, if_match="*")

        assert result == row
        assert row.goal_calories == 9000
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_missing_goal_is_not_found(self, mock_db):
        _one(mock_db, None)
        update = user_goals_schema.UsersGoalUpdate(
            interval="weekly", activity_type="run", goal_type="calories", goal_calories=9000
        )

        with pytest.raises(core_exceptions.NotFoundError):
            user_goals_crud.update_user_goal(1, 7, update, mock_db, if_match="*")


class TestDeleteUserGoal:
    def test_stages_the_deletion(self, mock_db):
        row = MagicMock(spec=user_goals_models.UsersGoal)
        _one(mock_db, row)

        user_goals_crud.delete_user_goal(1, 5, mock_db)

        mock_db.delete.assert_called_once_with(row)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_missing_goal_is_not_found(self, mock_db):
        _one(mock_db, None)

        with pytest.raises(core_exceptions.NotFoundError):
            user_goals_crud.delete_user_goal(1, 5, mock_db)


class TestGoalUniquenessInTheDatabase:
    """One goal per user, interval, activity type and goal type is the database's rule, so two requests cannot both win."""

    @pytest.fixture
    def db(self):
        session = create_sqlite_session()
        factory = sessionmaker(bind=session.get_bind())
        ensure_user(factory, 1)
        ensure_user(factory, 2)
        yield session
        session.close()

    @staticmethod
    def _goal(**overrides):
        values = {"interval": "weekly", "activity_type": "run", "goal_type": "calories", "goal_calories": 5000}
        values.update(overrides)
        return user_goals_schema.UsersGoalCreate(**values)

    def test_the_same_goal_twice_is_a_conflict(self, db):
        user_goals_crud.create_user_goal(1, self._goal(), db)

        with pytest.raises(core_exceptions.ConflictError):
            user_goals_crud.create_user_goal(1, self._goal(goal_calories=9000), db)

    def test_another_users_identical_goal_is_allowed(self, db):
        user_goals_crud.create_user_goal(1, self._goal(), db)

        user_goals_crud.create_user_goal(2, self._goal(), db)

    def test_editing_a_goal_into_another_one_is_a_conflict(self, db):
        user_goals_crud.create_user_goal(1, self._goal(), db)
        other = user_goals_crud.create_user_goal(1, self._goal(interval="monthly"), db)
        change = user_goals_schema.UsersGoalUpdate(**self._goal().model_dump())

        with pytest.raises(core_exceptions.ConflictError):
            user_goals_crud.update_user_goal(1, other.id, change, db, if_match="*")

    def test_replacing_a_goal_resets_the_targets_it_leaves_out(self, db):
        created = user_goals_crud.create_user_goal(
            1, self._goal(goal_type="distance", goal_calories=None, goal_distance=10000), db
        )
        # As a client sends it: the distance target is simply absent from the body.
        replacement = user_goals_schema.UsersGoalUpdate(
            interval="weekly", activity_type="run", goal_type="calories", goal_calories=5000
        )

        result = user_goals_crud.update_user_goal(1, created.id, replacement, db, if_match="*")

        assert result.goal_calories == 5000
        assert result.goal_distance is None
