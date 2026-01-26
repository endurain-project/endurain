import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import health.health_intraday_steps.crud as health_intraday_steps_crud
import health.health_intraday_steps.schema as health_intraday_steps_schema
import health.health_intraday_steps.models as health_intraday_steps_models


class TestGetAllHealthIntradayStepsByUserId:
    """
    Test suite for get_all_health_intraday_steps_by_user_id function.
    """

    def test_get_all_health_intraday_steps_by_user_id_success(self, mock_db):
        """
        Test successful retrieval of all health intraday steps records for user.
        """
        # Arrange
        user_id = 1
        mock_steps1 = MagicMock(spec=health_intraday_steps_models.HealthIntradaySteps)
        mock_steps2 = MagicMock(spec=health_intraday_steps_models.HealthIntradaySteps)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_steps1, mock_steps2]
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_execute

        # Act
        result = health_intraday_steps_crud.get_all_health_intraday_steps_by_user_id(user_id, mock_db)

        # Assert
        assert result == [mock_steps1, mock_steps2]
        mock_db.execute.assert_called_once()

    def test_get_all_health_intraday_steps_by_user_id_empty(self, mock_db):
        """
        Test retrieval when user has no health intraday steps records.
        """
        # Arrange
        user_id = 1
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_execute

        # Act
        result = health_intraday_steps_crud.get_all_health_intraday_steps_by_user_id(user_id, mock_db)

        # Assert
        assert result == []

    def test_get_all_health_intraday_steps_by_user_id_exception(self, mock_db):
        """
        Test exception handling in get_all_health_intraday_steps_by_user_id.
        """
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_intraday_steps_crud.get_all_health_intraday_steps_by_user_id(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestGetHealthIntradayStepsWithPagination:
    """
    Test suite for get_health_intraday_steps_with_pagination function.
    """

    def test_get_health_intraday_steps_with_pagination_success(self, mock_db):
        """
        Test successful retrieval of paginated health intraday steps records.
        """
        # Arrange
        user_id = 1
        page_number = 2
        num_records = 5
        mock_steps1 = MagicMock(spec=health_intraday_steps_models.HealthIntradaySteps)
        mock_steps2 = MagicMock(spec=health_intraday_steps_models.HealthIntradaySteps)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_steps1, mock_steps2]
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_execute

        # Act
        result = health_intraday_steps_crud.get_health_intraday_steps_with_pagination(
            user_id, mock_db, page_number, num_records
        )

        # Assert
        assert result == [mock_steps1, mock_steps2]
        mock_db.execute.assert_called_once()

    def test_get_health_intraday_steps_with_pagination_defaults(self, mock_db):
        """
        Test pagination with default values.
        """
        # Arrange
        user_id = 1
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_execute

        # Act
        result = health_intraday_steps_crud.get_health_intraday_steps_with_pagination(user_id, mock_db)

        # Assert
        assert result == []
        mock_db.execute.assert_called_once()

    def test_get_health_intraday_steps_with_pagination_exception(self, mock_db):
        """
        Test exception handling in get_health_intraday_steps_with_pagination.
        """
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_intraday_steps_crud.get_health_intraday_steps_with_pagination(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestGetHealthIntradayStepsByTimerange:
    """
    Test suite for get_health_intraday_steps_by_timerange function.
    """

    def test_get_health_intraday_steps_by_timerange_success(self, mock_db):
        """
        Test successful retrieval of health intraday steps by time range.
        """
        # Arrange
        user_id = 1
        start_time = datetime(2024, 1, 15, 0, 0, 0)
        end_time = datetime(2024, 1, 16, 0, 0, 0)
        mock_steps1 = MagicMock(spec=health_intraday_steps_models.HealthIntradaySteps)
        mock_steps2 = MagicMock(spec=health_intraday_steps_models.HealthIntradaySteps)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_steps1, mock_steps2]
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_execute

        # Act
        result = health_intraday_steps_crud.get_health_intraday_steps_by_timerange(
            user_id, start_time, end_time, mock_db
        )

        # Assert
        assert result == [mock_steps1, mock_steps2]
        mock_db.execute.assert_called_once()

    def test_get_health_intraday_steps_by_timerange_empty(self, mock_db):
        """
        Test retrieval when no records exist in time range.
        """
        # Arrange
        user_id = 1
        start_time = datetime(2024, 1, 15, 0, 0, 0)
        end_time = datetime(2024, 1, 16, 0, 0, 0)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_execute

        # Act
        result = health_intraday_steps_crud.get_health_intraday_steps_by_timerange(
            user_id, start_time, end_time, mock_db
        )

        # Assert
        assert result == []

    def test_get_health_intraday_steps_by_timerange_exception(self, mock_db):
        """
        Test exception handling in get_health_intraday_steps_by_timerange.
        """
        # Arrange
        user_id = 1
        start_time = datetime(2024, 1, 15, 0, 0, 0)
        end_time = datetime(2024, 1, 16, 0, 0, 0)
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_intraday_steps_crud.get_health_intraday_steps_by_timerange(
                user_id, start_time, end_time, mock_db
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestGetHealthIntradayStepsByIdAndUserId:
    """
    Test suite for get_health_intraday_steps_by_id_and_user_id function.
    """

    def test_get_health_intraday_steps_by_id_and_user_id_success(self, mock_db):
        """
        Test successful retrieval of health intraday steps by ID and user ID.
        """
        # Arrange
        health_intraday_steps_id = 1
        user_id = 1
        mock_steps = MagicMock(spec=health_intraday_steps_models.HealthIntradaySteps)
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_steps

        # Act
        result = health_intraday_steps_crud.get_health_intraday_steps_by_id_and_user_id(
            health_intraday_steps_id, user_id, mock_db
        )

        # Assert
        assert result == mock_steps
        mock_db.execute.assert_called_once()

    def test_get_health_intraday_steps_by_id_and_user_id_not_found(self, mock_db):
        """
        Test retrieval when record not found.
        """
        # Arrange
        health_intraday_steps_id = 999
        user_id = 1
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        result = health_intraday_steps_crud.get_health_intraday_steps_by_id_and_user_id(
            health_intraday_steps_id, user_id, mock_db
        )

        # Assert
        assert result is None

    def test_get_health_intraday_steps_by_id_and_user_id_exception(self, mock_db):
        """
        Test exception handling in get_health_intraday_steps_by_id_and_user_id.
        """
        # Arrange
        health_intraday_steps_id = 1
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_intraday_steps_crud.get_health_intraday_steps_by_id_and_user_id(
                health_intraday_steps_id, user_id, mock_db
            )

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestCreateHealthIntradaySteps:
    """
    Test suite for create_health_intraday_steps function.
    """

    def test_create_health_intraday_steps_success(self, mock_db):
        """
        Test successful creation of health intraday steps entry.
        """
        # Arrange
        user_id = 1
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        health_intraday_steps = [
            health_intraday_steps_schema.HealthIntradayStepsCreate(
                timestamp=test_timestamp,
                steps=1000,
                source="garmin",
            )
        ]

        mock_db_steps = MagicMock()
        mock_db_steps.id = 1
        mock_db_steps.steps = 1000
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None

        with patch.object(
            health_intraday_steps_models,
            "HealthIntradaySteps",
            return_value=mock_db_steps,
        ):
            # Act
            result = health_intraday_steps_crud.create_health_intraday_steps(
                user_id, health_intraday_steps, mock_db
            )

            # Assert
            assert len(result) == 1
            assert result[0].id == 1
            assert result[0].steps == 1000
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()
            mock_db.refresh.assert_called_once()

    def test_create_health_intraday_steps_multiple(self, mock_db):
        """
        Test successful creation of multiple health intraday steps entries.
        """
        # Arrange
        user_id = 1
        test_timestamp1 = datetime(2024, 1, 15, 10, 30, 0)
        test_timestamp2 = datetime(2024, 1, 15, 11, 30, 0)
        health_intraday_steps = [
            health_intraday_steps_schema.HealthIntradayStepsCreate(
                timestamp=test_timestamp1,
                steps=1000,
            ),
            health_intraday_steps_schema.HealthIntradayStepsCreate(
                timestamp=test_timestamp2,
                steps=1200,
            ),
        ]

        mock_db_steps1 = MagicMock()
        mock_db_steps1.id = 1
        mock_db_steps2 = MagicMock()
        mock_db_steps2.id = 2

        with patch.object(
            health_intraday_steps_models,
            "HealthIntradaySteps",
            side_effect=[mock_db_steps1, mock_db_steps2],
        ):
            # Act
            result = health_intraday_steps_crud.create_health_intraday_steps(
                user_id, health_intraday_steps, mock_db
            )

            # Assert
            assert len(result) == 2
            assert mock_db.add.call_count == 2
            assert mock_db.commit.call_count == 2

    def test_create_health_intraday_steps_duplicate_entry(self, mock_db):
        """
        Test creation with duplicate entry raises conflict error.
        """
        # Arrange
        user_id = 1
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        health_intraday_steps = [
            health_intraday_steps_schema.HealthIntradayStepsCreate(
                timestamp=test_timestamp, steps=1000, source="garmin"
            )
        ]

        mock_db_steps = MagicMock()
        mock_db.add.return_value = None
        mock_db.commit.side_effect = IntegrityError("Duplicate entry", None, None)

        with patch.object(
            health_intraday_steps_models,
            "HealthIntradaySteps",
            return_value=mock_db_steps,
        ):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                health_intraday_steps_crud.create_health_intraday_steps(user_id, health_intraday_steps, mock_db)

            assert exc_info.value.status_code == status.HTTP_409_CONFLICT
            assert "Duplicate entry error" in exc_info.value.detail
            mock_db.rollback.assert_called_once()

    def test_create_health_intraday_steps_exception(self, mock_db):
        """
        Test exception handling in create_health_intraday_steps.
        """
        # Arrange
        user_id = 1
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        health_intraday_steps = [
            health_intraday_steps_schema.HealthIntradayStepsCreate(
                timestamp=test_timestamp, steps=1000
            )
        ]

        mock_db.add.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_intraday_steps_crud.create_health_intraday_steps(user_id, health_intraday_steps, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        mock_db.rollback.assert_called_once()


class TestEditHealthIntradaySteps:
    """
    Test suite for edit_health_intraday_steps function.
    """

    def test_edit_health_intraday_steps_success(self, mock_db):
        """
        Test successful edit of health intraday steps entry.
        """
        # Arrange
        user_id = 1
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        health_intraday_steps = health_intraday_steps_schema.HealthIntradayStepsUpdate(
            id=1, user_id=1, timestamp=test_timestamp, steps=1200
        )

        mock_db_steps = MagicMock(spec=health_intraday_steps_models.HealthIntradaySteps)
        mock_db_steps.steps = 1200

        with patch.object(
            health_intraday_steps_crud,
            "get_health_intraday_steps_by_id_and_user_id",
            return_value=mock_db_steps,
        ):
            # Act
            result = health_intraday_steps_crud.edit_health_intraday_steps(user_id, health_intraday_steps, mock_db)

            # Assert
            assert result.steps == 1200
            mock_db.commit.assert_called_once()

    def test_edit_health_intraday_steps_not_found(self, mock_db):
        """
        Test edit when health intraday steps record not found.
        """
        # Arrange
        user_id = 1
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        health_intraday_steps = health_intraday_steps_schema.HealthIntradayStepsUpdate(
            id=999, user_id=1, timestamp=test_timestamp, steps=1200
        )

        with patch.object(
            health_intraday_steps_crud,
            "get_health_intraday_steps_by_id_and_user_id",
            return_value=None,
        ):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                health_intraday_steps_crud.edit_health_intraday_steps(user_id, health_intraday_steps, mock_db)

            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
            assert exc_info.value.detail == "Health intraday steps not found"

    def test_edit_health_intraday_steps_wrong_user(self, mock_db):
        """
        Test edit when trying to edit another user's record.
        """
        # Arrange
        user_id = 1
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        health_intraday_steps = health_intraday_steps_schema.HealthIntradayStepsUpdate(
            id=1, user_id=2, timestamp=test_timestamp, steps=1200
        )

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_intraday_steps_crud.edit_health_intraday_steps(user_id, health_intraday_steps, mock_db)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Cannot edit health intraday steps for another user" in exc_info.value.detail

    def test_edit_health_intraday_steps_update_multiple_fields(self, mock_db):
        """
        Test edit updates multiple fields correctly.
        """
        # Arrange
        user_id = 1
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        health_intraday_steps = health_intraday_steps_schema.HealthIntradayStepsUpdate(
            id=1,
            user_id=1,
            timestamp=test_timestamp,
            steps=1500,
            source="garmin",
        )

        mock_db_steps = MagicMock(spec=health_intraday_steps_models.HealthIntradaySteps)

        with patch.object(
            health_intraday_steps_crud,
            "get_health_intraday_steps_by_id_and_user_id",
            return_value=mock_db_steps,
        ):
            # Act
            result = health_intraday_steps_crud.edit_health_intraday_steps(user_id, health_intraday_steps, mock_db)

            # Assert
            mock_db.commit.assert_called_once()

    def test_edit_health_intraday_steps_exception(self, mock_db):
        """
        Test exception handling in edit_health_intraday_steps.
        """
        # Arrange
        user_id = 1
        test_timestamp = datetime(2024, 1, 15, 10, 30, 0)
        health_intraday_steps = health_intraday_steps_schema.HealthIntradayStepsUpdate(
            id=1, user_id=1, timestamp=test_timestamp, steps=1200
        )

        with patch.object(
            health_intraday_steps_crud,
            "get_health_intraday_steps_by_id_and_user_id",
            side_effect=SQLAlchemyError("Database error"),
        ):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                health_intraday_steps_crud.edit_health_intraday_steps(user_id, health_intraday_steps, mock_db)

            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            mock_db.rollback.assert_called_once()


class TestDeleteHealthIntradaySteps:
    """
    Test suite for delete_health_intraday_steps function.
    """

    def test_delete_health_intraday_steps_success(self, mock_db):
        """
        Test successful deletion of health intraday steps entry.
        """
        # Arrange
        user_id = 1
        health_intraday_steps_id = 1

        mock_db_steps = MagicMock(spec=health_intraday_steps_models.HealthIntradaySteps)

        with patch.object(
            health_intraday_steps_crud,
            "get_health_intraday_steps_by_id_and_user_id",
            return_value=mock_db_steps,
        ):
            # Act
            health_intraday_steps_crud.delete_health_intraday_steps(user_id, health_intraday_steps_id, mock_db)

            # Assert
            mock_db.delete.assert_called_once_with(mock_db_steps)
            mock_db.commit.assert_called_once()

    def test_delete_health_intraday_steps_not_found(self, mock_db):
        """
        Test deletion when health intraday steps record not found.
        """
        # Arrange
        user_id = 1
        health_intraday_steps_id = 999

        with patch.object(
            health_intraday_steps_crud,
            "get_health_intraday_steps_by_id_and_user_id",
            return_value=None,
        ):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                health_intraday_steps_crud.delete_health_intraday_steps(user_id, health_intraday_steps_id, mock_db)

            assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
            assert "Health intraday steps not found" in exc_info.value.detail

    def test_delete_health_intraday_steps_exception(self, mock_db):
        """
        Test exception handling in delete_health_intraday_steps.
        """
        # Arrange
        user_id = 1
        health_intraday_steps_id = 1

        with patch.object(
            health_intraday_steps_crud,
            "get_health_intraday_steps_by_id_and_user_id",
            side_effect=SQLAlchemyError("Database error"),
        ):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                health_intraday_steps_crud.delete_health_intraday_steps(user_id, health_intraday_steps_id, mock_db)

            assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            mock_db.rollback.assert_called_once()
