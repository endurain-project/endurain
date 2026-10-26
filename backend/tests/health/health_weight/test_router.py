from datetime import date as datetime_date
from unittest.mock import ANY, patch

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.health.health_weight.schema as health_weight_schema

_LIST = "modules.health.health_weight.router.health_weight_service.list_health_weight"


def _record(record_id: int, day: int, weight: float) -> health_weight_schema.HealthWeightRead:
    return health_weight_schema.HealthWeightRead(
        id=record_id, user_id=1, date=datetime_date(2024, 1, day), weight=weight, bmi=24.5
    )


class TestReadHealthWeightAll:
    @patch(_LIST)
    def test_returns_the_page_and_total(self, mock_list, fast_api_client, fast_api_app):
        mock_list.return_value = core_pagination.Page(
            items=[_record(1, 15, 75.5), _record(2, 16, 75.0)], total=2, page=1, num_records=25
        )

        response = fast_api_client.get("/health_weight", headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert [r["weight"] for r in data["items"]] == [75.5, 75.0]

    @patch(_LIST)
    def test_empty(self, mock_list, fast_api_client, fast_api_app):
        mock_list.return_value = core_pagination.Page(items=[], total=0, page=1, num_records=25)

        response = fast_api_client.get("/health_weight", headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 200
        assert response.json()["items"] == []

    @patch(_LIST)
    def test_passes_pagination_and_interval_through(self, mock_list, fast_api_client, fast_api_app):
        mock_list.return_value = core_pagination.Page(items=[], total=0, page=2, num_records=10)

        response = fast_api_client.get(
            "/health_weight?page_number=2&num_records=10&interval=last_30_days",
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.status_code == 200
        args = mock_list.call_args
        assert args.args[0] == 1
        assert (args.kwargs["page_number"], args.kwargs["num_records"]) == (2, 10)
        assert args.kwargs["interval"].value == "last_30_days"


class TestCreateHealthWeight:
    """
    Test suite for create_health_weight endpoint.
    """

    @patch("modules.health.health_weight.router.health_weight_service.create_health_weight")
    def test_create_health_weight_success(
        self,
        mock_create,
        fast_api_client,
        fast_api_app,
    ):
        """
        Test successful creation of health weight entry.
        """
        # Arrange
        created_weight = health_weight_schema.HealthWeightRead(
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


class TestEditHealthWeight:
    """
    Test suite for edit_health_weight endpoint.
    """

    @patch("modules.health.health_weight.router.health_weight_service.edit_health_weight")
    def test_edit_health_weight_success(self, mock_edit, fast_api_client, fast_api_app):
        """
        Test successful edit of health weight entry.
        """
        # Arrange
        updated_weight = health_weight_schema.HealthWeightRead(
            id=1,
            user_id=1,
            date=datetime_date(2024, 1, 15),
            weight=76.0,
            bmi=24.7,
        )
        mock_edit.return_value = updated_weight

        # Act
        response = fast_api_client.patch(
            "/health_weight/1",
            json={
                "date": "2024-01-15",
                "weight": 76.0,
            },
            headers={**{"Authorization": "Bearer mock_token"}, "If-Match": '"1"'},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["weight"] == 76.0

    @patch("modules.health.health_weight.router.health_weight_service.edit_health_weight")
    def test_edit_health_weight_not_found(self, mock_edit, fast_api_client, fast_api_app):
        """
        Test edit when health weight not found.
        """
        # Arrange
        mock_edit.side_effect = core_exceptions.NotFoundError("Health weight not found")

        # Act
        response = fast_api_client.patch(
            "/health_weight/999",
            json={
                "date": "2024-01-15",
                "weight": 76.0,
            },
            headers={**{"Authorization": "Bearer mock_token"}, "If-Match": '"1"'},
        )

        # Assert
        assert response.status_code == 404


class TestDeleteHealthWeight:
    """
    Test suite for delete_health_weight endpoint.
    """

    @patch("modules.health.health_weight.router.health_weight_service.delete_health_weight")
    def test_delete_health_weight_success(self, mock_delete, fast_api_client, fast_api_app):
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

    @patch("modules.health.health_weight.router.health_weight_service.delete_health_weight")
    def test_delete_health_weight_not_found(self, mock_delete, fast_api_client, fast_api_app):
        """
        Test deletion when health weight not found.
        """
        # Arrange
        mock_delete.side_effect = core_exceptions.NotFoundError("Health weight not found")

        # Act
        response = fast_api_client.delete(
            "/health_weight/999",
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 404
