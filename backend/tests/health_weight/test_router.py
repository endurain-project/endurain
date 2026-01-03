import pytest
from datetime import date as datetime_date
from unittest.mock import MagicMock, patch, ANY
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

import health.health_weight.schema as health_weight_schema
import health.health_weight.models as health_weight_models


class TestReadHealthWeightAll:
    """
    Test suite for read_health_weight_all endpoint.
    """

    @patch("health.health_weight.router.health_weight_crud.get_health_weight_number")
    @patch(
        "health.health_weight.router.health_weight_crud."
        "get_all_health_weight_by_user_id"
    )
    def test_read_health_weight_all_success(
        self, mock_get_all, mock_get_number, fast_api_client, fast_api_app
    ):
        """
        Test successful retrieval of all health weight records with total count.
        """
        # Arrange
        mock_weight1 = MagicMock(spec=health_weight_models.HealthWeight)
        mock_weight1.id = 1
        mock_weight1.user_id = 1
        mock_weight1.date = datetime_date(2024, 1, 15)
        mock_weight1.weight = 75.5
        mock_weight1.bmi = 24.5
        mock_weight1.source = None

        mock_weight2 = MagicMock(spec=health_weight_models.HealthWeight)
        mock_weight2.id = 2
        mock_weight2.user_id = 1
        mock_weight2.date = datetime_date(2024, 1, 16)
        mock_weight2.weight = 75.0
        mock_weight2.bmi = 24.3
        mock_weight2.source = None

        mock_get_all.return_value = [mock_weight1, mock_weight2]
        mock_get_number.return_value = 2

        # Act
        response = fast_api_client.get(
            "/health_weight",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["records"]) == 2

    @patch("health.health_weight.router.health_weight_crud.get_health_weight_number")
    @patch(
        "health.health_weight.router.health_weight_crud."
        "get_all_health_weight_by_user_id"
    )
    def test_read_health_weight_all_empty(
        self, mock_get_all, mock_get_number, fast_api_client, fast_api_app
    ):
        """
        Test retrieval when user has no health weight records.
        """
        # Arrange
        mock_get_all.return_value = []
        mock_get_number.return_value = 0

        # Act
        response = fast_api_client.get(
            "/health_weight",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["records"] == []


class TestReadHealthWeightAllPagination:
    """
    Test suite for read_health_weight_all_pagination endpoint.
    """

    @patch("health.health_weight.router.health_weight_crud.get_health_weight_number")
    @patch(
        "health.health_weight.router.health_weight_crud."
        "get_health_weight_with_pagination"
    )
    def test_read_health_weight_all_pagination_success(
        self, mock_get_paginated, mock_get_number, fast_api_client, fast_api_app
    ):
        """
        Test successful retrieval of paginated health weight records with total count.
        """
        # Arrange
        mock_weight1 = MagicMock(spec=health_weight_models.HealthWeight)
        mock_weight1.id = 1
        mock_weight1.user_id = 1
        mock_weight1.date = datetime_date(2024, 1, 15)
        mock_weight1.weight = 75.5
        mock_weight1.bmi = 24.5
        mock_weight1.source = None

        mock_get_paginated.return_value = [mock_weight1]
        mock_get_number.return_value = 10

        # Act
        response = fast_api_client.get(
            "/health_weight/page_number/1/num_records/5",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 10
        assert data["num_records"] == 5
        assert data["page_number"] == 1
        assert len(data["records"]) == 1

    @patch("health.health_weight.router.health_weight_crud.get_health_weight_number")
    @patch(
        "health.health_weight.router.health_weight_crud."
        "get_health_weight_with_pagination"
    )
    def test_read_health_weight_all_pagination_different_page(
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
            "/health_weight/page_number/2/num_records/10",
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


class TestCreateHealthWeight:
    """
    Test suite for create_health_weight endpoint.
    """

    @patch("health.health_weight.router.health_weight_crud.create_health_weight")
    @patch("health.health_weight.router.health_weight_crud.get_health_weight_by_date")
    def test_create_health_weight_success(
        self,
        mock_get_by_date,
        mock_create,
        fast_api_client,
        fast_api_app,
    ):
        """
        Test successful creation of health weight entry.
        """
        # Arrange
        mock_get_by_date.return_value = None
        created_weight = health_weight_schema.HealthWeight(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            weight=75.5,
            bmi=24.5,
        )
        mock_create.return_value = created_weight

        # Act
        response = fast_api_client.post(
            "/health_weight",
            json={
                "date": "2024-01-15",
                "weight": 75.5,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["weight"] == 75.5

    @patch("health.health_weight.router.health_weight_crud.edit_health_weight")
    @patch("health.health_weight.router.health_weight_crud.get_health_weight_by_date")
    def test_create_health_weight_updates_existing(
        self, mock_get_by_date, mock_edit, fast_api_client, fast_api_app
    ):
        """
        Test creating health weight when entry exists updates it.
        """
        # Arrange
        existing_weight = MagicMock()
        existing_weight.id = 1
        mock_get_by_date.return_value = existing_weight

        updated_weight = health_weight_schema.HealthWeight(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            weight=76.0,
            bmi=24.7,
        )
        mock_edit.return_value = updated_weight

        # Act
        response = fast_api_client.post(
            "/health_weight",
            json={
                "date": "2024-01-15",
                "weight": 76.0,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 201
        mock_edit.assert_called_once()


class TestEditHealthWeight:
    """
    Test suite for edit_health_weight endpoint.
    """

    @patch("health.health_weight.router.health_weight_crud.edit_health_weight")
    def test_edit_health_weight_success(self, mock_edit, fast_api_client, fast_api_app):
        """
        Test successful edit of health weight entry.
        """
        # Arrange
        updated_weight = health_weight_schema.HealthWeight(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            weight=76.0,
            bmi=24.7,
        )
        mock_edit.return_value = updated_weight

        # Act
        response = fast_api_client.put(
            "/health_weight",
            json={
                "id": 1,
                "date": "2024-01-15",
                "weight": 76.0,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["weight"] == 76.0

    @patch("health.health_weight.router.health_weight_crud.edit_health_weight")
    def test_edit_health_weight_not_found(
        self, mock_edit, fast_api_client, fast_api_app
    ):
        """
        Test edit when health weight not found.
        """
        # Arrange
        mock_edit.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health weight not found",
        )

        # Act
        response = fast_api_client.put(
            "/health_weight",
            json={
                "id": 999,
                "date": "2024-01-15",
                "weight": 76.0,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404


class TestDeleteHealthWeight:
    """
    Test suite for delete_health_weight endpoint.
    """

    @patch("health.health_weight.router.health_weight_crud.delete_health_weight")
    def test_delete_health_weight_success(
        self, mock_delete, fast_api_client, fast_api_app
    ):
        """
        Test successful deletion of health weight entry.
        """
        # Arrange
        mock_delete.return_value = None

        # Act
        response = fast_api_client.delete(
            "/health_weight/1",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 204
        mock_delete.assert_called_once_with(1, 1, ANY)

    @patch("health.health_weight.router.health_weight_crud.delete_health_weight")
    def test_delete_health_weight_not_found(
        self, mock_delete, fast_api_client, fast_api_app
    ):
        """
        Test deletion when health weight not found.
        """
        # Arrange
        mock_delete.side_effect = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Health weight with id 999 for user 1 not found",
        )

        # Act
        response = fast_api_client.delete(
            "/health_weight/999",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404
