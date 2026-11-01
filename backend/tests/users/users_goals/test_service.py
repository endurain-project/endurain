"""Tests for users.users_goals.service module."""

from unittest.mock import patch

import pytest
from sqlalchemy.orm.exc import StaleDataError

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.users.users_goals.schema as user_goals_schema
import modules.users.users_goals.service as user_goals_service


@patch("modules.users.users_goals.service.user_goals_crud")
class TestUserGoalsService:
    def test_create_commits(self, mock_crud, mock_db):
        goal = user_goals_schema.UsersGoalCreate(
            interval="weekly", activity_type="run", goal_type="calories", goal_calories=5000
        )

        result = user_goals_service.create_goal(1, goal, mock_db)

        assert result == mock_crud.create_user_goal.return_value
        mock_db.commit.assert_called_once()

    def test_list_returns_a_page_with_the_total(self, mock_crud, mock_db):
        goal = user_goals_schema.UsersGoalRead(
            id=1, user_id=1, interval="weekly", activity_type="run", goal_type="calories", goal_calories=5000
        )
        mock_crud.get_user_goals_page.return_value = [goal]
        mock_crud.count_user_goals.return_value = 30

        page = user_goals_service.list_goals(1, core_pagination.PageParams(2, 25), mock_db)

        assert (page.items, page.total, page.page, page.next) == ([goal], 30, 2, None)
        assert mock_crud.get_user_goals_page.call_args.kwargs == {"limit": 25, "offset": 25}

    def test_update_commits(self, mock_crud, mock_db):
        goal = user_goals_schema.UsersGoalUpdate(
            interval="weekly", activity_type="run", goal_type="calories", goal_calories=5000
        )

        result = user_goals_service.update_goal(1, 7, goal, mock_db, if_match="*")

        assert result == mock_crud.update_user_goal.return_value
        mock_crud.update_user_goal.assert_called_once_with(1, 7, goal, mock_db, if_match="*")
        mock_db.commit.assert_called_once()

    def test_delete_commits(self, mock_crud, mock_db):
        user_goals_service.delete_goal(1, 5, mock_db, if_match='"2"')

        mock_crud.delete_user_goal.assert_called_once_with(1, 5, mock_db, if_match='"2"')
        mock_db.commit.assert_called_once()

    def test_a_delete_that_races_past_the_check_is_a_precondition_failure(self, mock_crud, mock_db):
        mock_crud.delete_user_goal.side_effect = StaleDataError("row changed")
        mock_crud.user_goal_exists.return_value = True

        with pytest.raises(core_exceptions.PreconditionFailedError):
            user_goals_service.delete_goal(1, 5, mock_db, if_match='"2"')

        mock_db.commit.assert_not_called()

    @pytest.mark.parametrize(
        ("call", "message"),
        [
            (lambda db: user_goals_service.create_goal(1, _goal_create(), db), "User goal created"),
            (lambda db: user_goals_service.update_goal(1, 7, _goal_create(), db, if_match="*"), "User goal updated"),
            (lambda db: user_goals_service.delete_goal(1, 5, db, if_match='"2"'), "User goal deleted"),
        ],
    )
    def test_a_completed_change_is_logged_once_at_info(self, mock_crud, mock_db, call, message, caplog):
        with caplog.at_level("DEBUG", logger=user_goals_service.logger.name):
            call(mock_db)

        assert [(record.levelname, record.getMessage()) for record in caplog.records] == [("INFO", message)]


def _goal_create():
    return user_goals_schema.UsersGoalCreate(
        interval="weekly", activity_type="run", goal_type="calories", goal_calories=5000
    )
