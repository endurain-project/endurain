import pytest
from datetime import date as datetime_date
from unittest.mock import MagicMock, patch, ANY
from fastapi import HTTPException, status

import health.health_steps.models as health_steps_models


class TestReadHealthStepsAll:
    """
    Test suite for read_health_steps_all endpoint.
    """

    @patch("health.health_steps.router.health_steps_crud.get_health_steps_number")
    @patch(
        "health.health_steps.router.health_steps_crud.get_all_health_steps_by_user_id"
    )
    def test_read_health_steps_all_success(
        self, mock_get_all, mock_get_number, fast_api_client, fast_api_app
    ):
        """
        Test successful retrieval of all health steps records with total count.
        """
        # Arrange
        mock_steps1 = MagicMock(spec=health_steps_models.HealthSteps)
        mock_steps1.id = 1
        mock_steps1.user_id = 1
        mock_steps1.date = datetime_date(2024, 1, 15)
        mock_steps1.steps = 10000
        mock_steps1.source = None

        mock_steps2 = MagicMock(spec=health_steps_models.HealthSteps)
        mock_steps2.id = 2
        mock_steps2.user_id = 1
        mock_steps2.date = datetime_date(2024, 1, 16)
        mock_steps2.steps = 12000
        mock_steps2.source = None

        mock_get_all.return_value = [mock_steps1, mock_steps2]
        mock_get_number.return_value = 2

        # Act
        response = fast_api_client.get(
            "/health_steps",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["records"]) == 2

    @patch("health.health_steps.router.health_steps_crud.get_health_steps_number")
    @patch(
        "health.health_steps.router.health_steps_crud.get_all_health_steps_by_user_id"
    )
    def test_read_health_steps_all_empty(
        self, mock_get_all, mock_get_number, fast_api_client, fast_api_app
    ):
        """
        Test retrieval when user has no health steps records.
        """
        # Arrange
        mock_get_all.return_value = []
        mock_get_number.return_value = 0

        # Act
        response = fast_api_client.get(
            "/health_steps",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["records"] == []


class TestReadHealthStepsAllPagination:
    """
    Test suite for read_health_steps_all_pagination endpoint.
    """

    @patch("health.health_steps.router.health_steps_crud.get_health_steps_number")
    @patch(
        "health.health_steps.router.health_steps_crud.get_health_steps_with_pagination"
    )
    def test_read_health_steps_all_pagination_success(
        self, mock_get_paginated, mock_get_number, fast_api_client, fast_api_app
    ):
        """
        Test successful retrieval of paginated health steps records with total count.
        """
        # Arrange
        mock_steps1 = MagicMock(spec=health_steps_models.HealthSteps)
        mock_steps1.id = 1
        mock_steps1.user_id = 1
        mock_steps1.date = datetime_date(2024, 1, 15)
        mock_steps1.steps = 10000
        mock_steps1.source = None

        mock_get_paginated.return_value = [mock_steps1]
        mock_get_number.return_value = 10

        # Act
        response = fast_api_client.get(
            "/health_steps/page_number/1/num_records/5",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 10
        assert data["num_records"] == 5
        assert data["page_number"] == 1
        assert len(data["records"]) == 1

    @patch("health.health_steps.router.health_steps_crud.get_health_steps_number")
    @patch(
        "health.health_steps.router.health_steps_crud.get_health_steps_with_pagination"
    )
    def test_read_health_steps_all_pagination_different_page(
        self, mock_get_paginated, mock_get_number, fast_api_client, fast_api_app
    ):
        """
        Test paginated retrieval with different page numbers.
        """
        # Arrange
        mock_get_paginated.return_value = []
        mock_get_number.return_value = 20

        # Act
        response = fast_api_client.get(
            "/health_steps/page_number/2/num_records/10",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 20
        assert data["num_records"] == 10
        assert data["page_number"] == 2
        assert data["records"] == []
        mock_get_paginated.assert_called_once_with(1, ANY, 2, 10)


class TestCreateHealthSteps:
    """
    Test suite for create_health_steps endpoint.
    """

    @patch("health.health_steps.router.health_steps_crud.create_health_steps")
    @patch("health.health_steps.router.health_steps_crud.get_health_steps_by_date")
    def test_create_health_steps_success(
        self,
        mock_get_by_date,
        mock_create,
        fast_api_client,
        fast_api_app,
    ):
        """
        Test successful creation of health steps entry.
        """
        # Arrange
        mock_get_by_date.return_value = None
        created_steps = MagicMock()
        created_steps.id = 1
        created_steps.user_id = 1
        created_steps.date = datetime_date(2024, 1, 15)
        created_steps.steps = 10000
        created_steps.source = None
        mock_create.return_value = created_steps

        # Act
        response = fast_api_client.post(
            "/health_steps",
            json={
                "date": "2024-01-15",
                "steps": 10000,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["steps"] == 10000

    @patch("health.health_steps.router.health_steps_crud.edit_health_steps")
    @patch("health.health_steps.router.health_steps_crud.get_health_steps_by_date")
    def test_create_health_steps_updates_existing(
        self, mock_get_by_date, mock_edit, fast_api_client, fast_api_app
    ):
        """
        Test creating health steps when entry exists updates it.
        """
        # Arrange
        existing_steps = MagicMock()
        existing_steps.id = 1
        mock_get_by_date.return_value = existing_steps

        updated_steps = MagicMock()
        updated_steps.id = 1
        updated_steps.user_id = 1
        updated_steps.date = datetime_date(2024, 1, 15)
        updated_steps.steps = 12000
        updated_steps.source = None
        mock_edit.return_value = updated_steps

        # Act
        response = fast_api_client.post(
            "/health_steps",
            json={
                "date": "2024-01-15",
                "steps": 12000,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 201
        mock_edit.assert_called_once()

    @patch("health.health_steps.router.health_steps_crud.create_health_steps")
    @patch("health.health_steps.router.health_steps_crud.get_health_steps_by_date")
    def test_create_health_steps_missing_date_uses_today(
        self, mock_get_by_date, mock_create, fast_api_client, fast_api_app
    ):
        """
        Test creating health steps without date uses today's date automatically.
        """
        # Arrange
        mock_get_by_date.return_value = None
        created_steps = MagicMock()
        created_steps.id = 1
        created_steps.user_id = 1
        created_steps.date = None  # Will be set by schema
        created_steps.steps = 10000
        created_steps.source = None
        mock_create.return_value = created_steps

        # Act
        response = fast_api_client.post(
            "/health_steps",
            json={
                "steps": 10000,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert - Now succeeds since HealthStepsCreate auto-fills date
        assert response.status_code == 201
        mock_create.assert_called_once()


class TestEditHealthSteps:
    """
    Test suite for edit_health_steps endpoint.
    """

    @patch("health.health_steps.router.health_steps_crud.edit_health_steps")
    def test_edit_health_steps_success(self, mock_edit, fast_api_client, fast_api_app):
        """
        Test successful edit of health steps entry.
        """
        # Arrange
        updated_steps = MagicMock()
        updated_steps.id = 1
        updated_steps.user_id = 1
        updated_steps.date = datetime_date(2024, 1, 15)
        updated_steps.steps = 12000
        updated_steps.source = None
        mock_edit.return_value = updated_steps

        # Act
        response = fast_api_client.put(
            "/health_steps",
            json={
                "id": 1,
                "user_id": 1,
                "date": "2024-01-15",
                "steps": 12000,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["steps"] == 12000

    @patch("health.health_steps.router.health_steps_crud.edit_health_steps")
    def test_edit_health_steps_not_found(
        self, mock_edit, fast_api_client, fast_api_app
    ):
        """
        Test edit when health steps not found.
        """
        # Arrange
        mock_edit.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health steps not found",
        )

        # Act
        response = fast_api_client.put(
            "/health_steps",
            json={
                "id": 999,
                "user_id": 1,
                "date": "2024-01-15",
                "steps": 12000,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404


class TestDeleteHealthSteps:
    """
    Test suite for delete_health_steps endpoint.
    """

    @patch("health.health_steps.router.health_steps_crud.delete_health_steps")
    def test_delete_health_steps_success(
        self, mock_delete, fast_api_client, fast_api_app
    ):
        """
        Test successful deletion of health steps entry.
        """
        # Arrange
        mock_delete.return_value = None

        # Act
        response = fast_api_client.delete(
            "/health_steps/1",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204
        mock_delete.assert_called_once_with(1, 1, ANY)

    @patch("health.health_steps.router.health_steps_crud.delete_health_steps")
    def test_delete_health_steps_not_found(
        self, mock_delete, fast_api_client, fast_api_app
    ):
        """
        Test deletion when health steps not found.
        """
        # Arrange
        mock_delete.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health steps with id 999 for user 1 not found",
        )

        # Act
        response = fast_api_client.delete(
            "/health_steps/999",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404
