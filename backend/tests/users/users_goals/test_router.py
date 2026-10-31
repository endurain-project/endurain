"""Tests for user goals API endpoints."""

from unittest.mock import MagicMock, patch

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.users.users_goals.models as user_goals_models
import modules.users.users_goals.schema as user_goals_schema


class TestGetUserGoals:
    """
    Test suite for get_user_goals endpoint.
    """

    @patch("modules.users.users_goals.router.user_goals_service.list_goals")
    def test_get_user_goals_success(self, mock_get_goals, fast_api_client, fast_api_app):
        """Test successful retrieval of all user goals."""
        # Arrange
        mock_goal1 = MagicMock(spec=user_goals_models.UsersGoal)
        mock_goal1.id = 1
        mock_goal1.user_id = 1
        mock_goal1.version = 1
        mock_goal1.interval = "weekly"
        mock_goal1.activity_type = "run"
        mock_goal1.goal_type = "calories"
        mock_goal1.goal_calories = 5000
        mock_goal1.goal_activities_number = None
        mock_goal1.goal_distance = None
        mock_goal1.goal_elevation = None
        mock_goal1.goal_duration = None

        mock_get_goals.return_value = user_goals_schema.UsersGoalPage.build(
            [user_goals_schema.UsersGoalRead.model_validate(mock_goal1)], 1, 1, 25
        )

        # Act
        response = fast_api_client.get(
            "/user_goals",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert (data["total"], data["next"]) == (1, None)

    @patch("modules.users.users_goals.router.user_goals_service.list_goals")
    def test_get_user_goals_empty(self, mock_get_goals, fast_api_client, fast_api_app):
        """Test retrieval when user has no goals."""
        # Arrange
        mock_get_goals.return_value = user_goals_schema.UsersGoalPage.build([], 0, 1, 25)

        # Act
        response = fast_api_client.get(
            "/user_goals",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        assert response.json()["items"] == []


class TestGetUserGoalsResults:
    """
    Test suite for get_user_goals_results endpoint.
    """

    @patch("modules.users.users_goals.router.user_goals_progress_service.get_goals_progress")
    def test_get_user_goals_results_success(self, mock_calculate, fast_api_client, fast_api_app):
        """Returns the page of goal progress and forwards the window."""
        progress = user_goals_schema.UsersGoalProgress(
            goal_id=1,
            interval="weekly",
            activity_type="run",
            goal_type="calories",
            start_date="2024-01-15",
            end_date="2024-01-21",
            percentage_completed=75,
            total_calories=3750,
            goal_calories=5000,
        )
        mock_calculate.return_value = user_goals_schema.UsersGoalProgressPage.build([progress], 3, 2, 1)

        response = fast_api_client.get(
            "/user_goals/results?page_number=2&num_records=1",
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert [item["goal_id"] for item in data["items"]] == [1]
        assert (data["total"], data["page"], data["num_records"], data["next"]) == (3, 2, 1, 3)
        assert mock_calculate.call_args.args[0] == 1
        assert mock_calculate.call_args.args[1] == core_pagination.PageParams(2, 1)

    @patch("modules.users.users_goals.router.user_goals_progress_service.get_goals_progress")
    def test_get_user_goals_results_none(self, mock_calculate, fast_api_client, fast_api_app):
        """Returns an empty page when there are no goals."""
        mock_calculate.return_value = user_goals_schema.UsersGoalProgressPage.build([], 0, 1, 25)

        response = fast_api_client.get(
            "/user_goals/results",
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 200
        assert response.json()["items"] == []
        assert mock_calculate.call_args.args[1] == core_pagination.PageParams(1, 25)

    def test_get_user_goals_results_rejects_oversized_page(self, fast_api_client, fast_api_app):
        """A page size above the cap is a validation error."""
        response = fast_api_client.get(
            "/user_goals/results?num_records=201",
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 422


class TestCreateUserGoal:
    """
    Test suite for create_user_goal endpoint.
    """

    @patch("modules.users.users_goals.router.user_goals_service.create_goal")
    def test_create_user_goal_success(self, mock_create, fast_api_client, fast_api_app):
        """Test successful goal creation."""
        # Arrange
        mock_created_goal = MagicMock(spec=user_goals_models.UsersGoal)
        mock_created_goal.id = 1
        mock_created_goal.user_id = 1
        mock_created_goal.version = 1
        mock_created_goal.interval = "weekly"
        mock_created_goal.activity_type = "run"
        mock_created_goal.goal_type = "calories"
        mock_created_goal.goal_calories = 5000
        mock_created_goal.goal_activities_number = None
        mock_created_goal.goal_distance = None
        mock_created_goal.goal_elevation = None
        mock_created_goal.goal_duration = None

        mock_create.return_value = mock_created_goal

        # Act
        response = fast_api_client.post(
            "/user_goals",
            headers={"Authorization": "Bearer mock_token"},
            json={
                "interval": "weekly",
                "activity_type": "run",
                "goal_type": "calories",
                "goal_calories": 5000,
                "goal_activities_number": None,
                "goal_distance": None,
                "goal_elevation": None,
                "goal_duration": None,
            },
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 1
        assert data["goal_calories"] == 5000

    def test_create_user_goal_invalid_data(self, fast_api_client, fast_api_app):
        """Test creation fails with invalid data."""
        # Act
        response = fast_api_client.post(
            "/user_goals",
            headers={"Authorization": "Bearer mock_token"},
            json={
                "interval": "invalid",  # Invalid interval
                "activity_type": 1,
                "goal_type": 1,
                "goal_calories": 5000,
            },
        )

        # Assert
        assert response.status_code == 422


class TestUpdateUserGoal:
    """
    Test suite for update_user_goal endpoint.
    """

    @patch("modules.users.users_goals.router.user_goals_service.update_goal")
    def test_update_user_goal_success(
        self,
        mock_update,
        fast_api_client,
        fast_api_app,
    ):
        """Test successful goal update."""
        # Arrange
        mock_update.return_value = user_goals_schema.UsersGoalRead(
            id=1,
            user_id=1,
            interval=user_goals_schema.Interval.MONTHLY,
            activity_type=user_goals_schema.ActivityType.RUN,
            goal_type=user_goals_schema.GoalType.CALORIES,
            goal_calories=10000,
            goal_activities_number=None,
            goal_distance=None,
            goal_elevation=None,
            goal_duration=None,
        )

        # Act
        response = fast_api_client.put(
            "/user_goals/1",
            headers={"Authorization": "Bearer mock_token", "If-Match": '"1"'},
            json={
                "interval": "monthly",
                "activity_type": "run",  # RUN
                "goal_type": "calories",  # CALORIES
                "goal_calories": 10000,
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["goal_calories"] == 10000

    @patch("modules.users.users_goals.router.user_goals_service.update_goal")
    def test_update_user_goal_not_found(
        self,
        mock_update,
        fast_api_client,
        fast_api_app,
    ):
        """Test update fails when goal not found."""
        # Arrange
        mock_update.side_effect = core_exceptions.NotFoundError("User goal not found")

        # Act
        response = fast_api_client.put(
            "/user_goals/999",
            headers={"Authorization": "Bearer mock_token", "If-Match": '"1"'},
            json={
                "interval": "weekly",
                "activity_type": "run",
                "goal_type": "calories",
                "goal_calories": 5000,
                "goal_activities_number": None,
                "goal_distance": None,
                "goal_elevation": None,
                "goal_duration": None,
            },
        )

        # Assert
        assert response.status_code == 404


class TestDeleteUserGoal:
    """
    Test suite for delete_user_goal endpoint.
    """

    @patch("modules.users.users_goals.router.user_goals_service.delete_goal")
    def test_delete_user_goal_success(
        self,
        mock_delete,
        fast_api_client,
        fast_api_app,
    ):
        """Test successful goal deletion."""
        # Arrange
        mock_delete.return_value = None

        # Act
        response = fast_api_client.delete(
            "/user_goals/1",
            headers={"Authorization": "Bearer mock_token", "If-Match": '"3"'},
        )

        # Assert
        assert response.status_code == 204
        assert response.content == b""
        assert mock_delete.call_args.kwargs == {"if_match": '"3"'}

    @patch("modules.users.users_goals.router.user_goals_service.delete_goal")
    def test_delete_user_goal_not_found(
        self,
        mock_delete,
        fast_api_client,
        fast_api_app,
    ):
        """Test deletion fails when goal not found."""
        # Arrange
        mock_delete.side_effect = core_exceptions.NotFoundError("User goal not found")

        # Act
        response = fast_api_client.delete(
            "/user_goals/999",
            headers={"Authorization": "Bearer mock_token", "If-Match": '"1"'},
        )

        # Assert
        assert response.status_code == 404

    @patch("modules.users.users_goals.router.user_goals_service.delete_goal")
    def test_delete_without_if_match_is_428(self, mock_delete, fast_api_client):
        response = fast_api_client.delete("/user_goals/1", headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 428
        mock_delete.assert_not_called()

    @patch("modules.users.users_goals.router.user_goals_service.delete_goal")
    def test_a_stale_delete_is_412(self, mock_delete, fast_api_client):
        mock_delete.side_effect = core_exceptions.PreconditionFailedError("stale")

        response = fast_api_client.delete(
            "/user_goals/1", headers={"Authorization": "Bearer mock_token", "If-Match": '"1"'}
        )

        assert response.status_code == 412


class TestUpdateNeedsIfMatch:
    def test_an_update_without_if_match_is_428(self, fast_api_client):
        response = fast_api_client.put(
            "/user_goals/1",
            json={"interval": "weekly", "activity_type": "run", "goal_type": "calories", "goal_calories": 5000},
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 428
