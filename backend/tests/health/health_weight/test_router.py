import uuid
from datetime import date as datetime_date
from unittest.mock import ANY, patch

from tests._helpers.auth import MOCK_USER_ID

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.health.health_weight.schema as health_weight_schema

_LIST = "modules.health.health_weight.router.health_weight_service.list_health_weight"
_ID = uuid.uuid4()
_OTHER_ID = uuid.uuid4()


_USER_ID = MOCK_USER_ID


def _record(record_id: uuid.UUID, day: int, weight: float) -> health_weight_schema.HealthWeightRead:
    return health_weight_schema.HealthWeightRead(
        updated_at="2024-01-01T00:00:00Z",
        id=record_id,
        user_id=_USER_ID,
        date=datetime_date(2024, 1, day),
        weight_kg=weight,
        bmi=24.5,
    )


class TestReadHealthWeightAll:
    @patch(_LIST)
    def test_returns_the_page_and_total(self, mock_list, fast_api_client, fast_api_app):
        mock_list.return_value = core_pagination.Page(
            items=[_record(uuid.uuid4(), 15, 75.5), _record(uuid.uuid4(), 16, 75.0)], total=2, page=1, num_records=25
        )

        response = fast_api_client.get("/health_weight", headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert [r["weight_kg"] for r in data["items"]] == [75.5, 75.0]

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
        assert args.args[0] == _USER_ID
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
            updated_at="2024-01-01T00:00:00Z",
            id=_ID,
            user_id=_USER_ID,
            date=datetime_date(2024, 1, 15),
            weight_kg=75.5,
            bmi=24.5,
        )
        mock_create.return_value = created_weight

        # Act
        response = fast_api_client.post(
            "/health_weight",
            json={
                "date": "2024-01-15",
                "weight_kg": 75.5,
            },
            headers={"Authorization": "Bearer mock_token"},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["weight_kg"] == 75.5


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
            updated_at="2024-01-01T00:00:00Z",
            id=_ID,
            user_id=_USER_ID,
            date=datetime_date(2024, 1, 15),
            weight_kg=76.0,
            bmi=24.7,
        )
        mock_edit.return_value = updated_weight

        # Act
        response = fast_api_client.patch(
            f"/health_weight/{_ID}",
            json={
                "date": "2024-01-15",
                "weight_kg": 76.0,
            },
            headers={**{"Authorization": "Bearer mock_token"}, "If-Match": '"1"'},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["weight_kg"] == 76.0

    @patch("modules.health.health_weight.router.health_weight_service.edit_health_weight")
    def test_edit_health_weight_not_found(self, mock_edit, fast_api_client, fast_api_app):
        """
        Test edit when health weight not found.
        """
        # Arrange
        mock_edit.side_effect = core_exceptions.NotFoundError("Health weight not found")

        # Act
        response = fast_api_client.patch(
            f"/health_weight/{_OTHER_ID}",
            json={
                "date": "2024-01-15",
                "weight_kg": 76.0,
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
            f"/health_weight/{_ID}",
            headers={"Authorization": "Bearer mock_token", "If-Match": '"1"'},
        )

        # Assert
        assert response.status_code == 204
        mock_delete.assert_called_once_with(_USER_ID, _ID, ANY, if_match='"1"')

    @patch("modules.health.health_weight.router.health_weight_service.delete_health_weight")
    def test_delete_health_weight_not_found(self, mock_delete, fast_api_client, fast_api_app):
        """
        Test deletion when health weight not found.
        """
        # Arrange
        mock_delete.side_effect = core_exceptions.NotFoundError("Health weight not found")

        # Act
        response = fast_api_client.delete(
            f"/health_weight/{_OTHER_ID}",
            headers={"Authorization": "Bearer mock_token", "If-Match": '"1"'},
        )

        # Assert
        assert response.status_code == 404


_GET = "modules.health.health_weight.router.health_weight_service.get_health_weight"


class TestReadHealthWeightById:
    @patch(_GET)
    def test_returns_the_record_with_its_etag(self, mock_get, fast_api_client, fast_api_app):
        mock_get.return_value = _record(_ID, 15, 75.5)

        response = fast_api_client.get(f"/health_weight/{_ID}", headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        assert mock_get.call_args.args[:2] == (_USER_ID, _ID)

    @patch(_GET)
    def test_a_record_the_user_does_not_have_is_404(self, mock_get, fast_api_client, fast_api_app):
        mock_get.side_effect = core_exceptions.NotFoundError("Health weight not found")

        response = fast_api_client.get(f"/health_weight/{_OTHER_ID}", headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 404


class TestCreateHealthWeightHeaders:
    @patch("modules.health.health_weight.router.health_weight_service.create_health_weight")
    def test_create_names_the_record_and_its_version(self, mock_create, fast_api_client, fast_api_app):
        mock_create.return_value = _record(_ID, 15, 75.5)

        response = fast_api_client.post(
            "/health_weight",
            json={"date": "2024-01-15", "weight_kg": 75.5},
            headers={"Authorization": "Bearer mock_token"},
        )

        assert response.headers["Location"] == f"/health_weight/{_ID}"
        assert response.headers["ETag"] == '"1"'


class TestMalformedId:
    def test_a_malformed_id_is_422(self, fast_api_client, fast_api_app):
        response = fast_api_client.get("/health_weight/not-a-uuid", headers={"Authorization": "Bearer mock_token"})

        assert response.status_code == 422
