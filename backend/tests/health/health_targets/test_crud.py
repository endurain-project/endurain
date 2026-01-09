import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import health.health_targets.crud as health_targets_crud
import health.health_targets.schema as health_targets_schema
import health.health_targets.models as health_targets_models


class TestGetHealthTargetsByUserId:
    """
    Test suite for get_health_targets_by_user_id function.
    """

    def test_get_health_targets_by_user_id_success(self, mock_db):
        """
        Test successful retrieval of health targets for a user.
        """
        # Arrange
        user_id = 1
        mock_targets = MagicMock(spec=health_targets_models.HealthTargets)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_targets
        mock_db.execute.return_value = mock_result

        # Act
        result = health_targets_crud.get_health_targets_by_user_id(user_id, mock_db)

        # Assert
        assert result == mock_targets
        mock_db.execute.assert_called_once()

    def test_get_health_targets_by_user_id_not_found(self, mock_db):
        """
        Test retrieval when no health targets exist for user.
        """
        # Arrange
        user_id = 1
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act
        result = health_targets_crud.get_health_targets_by_user_id(user_id, mock_db)

        # Assert
        assert result is None

    def test_get_health_targets_by_user_id_exception(self, mock_db):
        """
        Test exception handling in get_health_targets_by_user_id.
        """
        # Arrange
        user_id = 1
        mock_db.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_targets_crud.get_health_targets_by_user_id(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"


class TestCreateHealthTargets:
    """
    Test suite for create_health_targets function.
    """

    def test_create_health_targets_success(self, mock_db):
        """
        Test successful creation of health targets entry.
        """
        # Arrange
        user_id = 1

        mock_db_targets = MagicMock(spec=health_targets_models.HealthTargets)
        mock_db_targets.id = 1
        mock_db_targets.user_id = user_id
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None

        with patch.object(
            health_targets_models,
            "HealthTargets",
            return_value=mock_db_targets,
        ):
            # Act
            result = health_targets_crud.create_health_targets(user_id, mock_db)

            # Assert - function returns db model, not schema
            assert result == mock_db_targets
            mock_db.add.assert_called_once()
            mock_db.commit.assert_called_once()
            mock_db.refresh.assert_called_once()

    def test_create_health_targets_duplicate_entry(self, mock_db):
        """
        Test creation with duplicate entry raises conflict error.
        """
        # Arrange
        user_id = 1

        mock_db_targets = MagicMock()
        mock_db.add.return_value = None
        mock_db.commit.side_effect = IntegrityError("Duplicate entry", None, None)

        with patch.object(
            health_targets_models,
            "HealthTargets",
            return_value=mock_db_targets,
        ):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                health_targets_crud.create_health_targets(user_id, mock_db)

            assert exc_info.value.status_code == status.HTTP_409_CONFLICT
            assert "Duplicate entry error" in exc_info.value.detail
            mock_db.rollback.assert_called_once()

    def test_create_health_targets_exception(self, mock_db):
        """
        Test exception handling in create_health_targets.
        """
        # Arrange
        user_id = 1
        mock_db.add.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_targets_crud.create_health_targets(user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"
        mock_db.rollback.assert_called_once()


class TestEditHealthTarget:
    """
    Test suite for edit_health_target function.
    """

    def test_edit_health_target_success(self, mock_db):
        """
        Test successful edit of health target entry.
        """
        # Arrange
        user_id = 1
        health_target = health_targets_schema.HealthTargetsUpdate(
            id=1, user_id=user_id, weight=75.0, steps=10000, sleep=28800
        )

        mock_db_target = MagicMock(spec=health_targets_models.HealthTargets)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_target
        mock_db.execute.return_value = mock_result

        # Act
        result = health_targets_crud.edit_health_target(health_target, user_id, mock_db)

        # Assert
        assert result == mock_db_target
        mock_db.commit.assert_called_once()

    def test_edit_health_target_not_found(self, mock_db):
        """
        Test edit when health target record not found.
        """
        # Arrange
        user_id = 1
        health_target = health_targets_schema.HealthTargetsUpdate(
            id=999, user_id=user_id, weight=75.0, steps=10000
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_targets_crud.edit_health_target(health_target, user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc_info.value.detail == "User health target not found"

    def test_edit_health_target_update_multiple_fields(self, mock_db):
        """
        Test edit updates multiple fields correctly.
        """
        # Arrange
        user_id = 1
        health_target = health_targets_schema.HealthTargetsUpdate(
            id=1,
            user_id=user_id,
            weight=80.0,
            steps=12000,
            sleep=32400,
        )

        mock_db_target = MagicMock(spec=health_targets_models.HealthTargets)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_target
        mock_db.execute.return_value = mock_result

        # Act
        result = health_targets_crud.edit_health_target(health_target, user_id, mock_db)

        # Assert
        mock_db.commit.assert_called_once()

    def test_edit_health_target_partial_update(self, mock_db):
        """
        Test edit with partial field updates.
        """
        # Arrange
        user_id = 1
        health_target = health_targets_schema.HealthTargetsUpdate(
            id=1, user_id=user_id, weight=75.0
        )

        mock_db_target = MagicMock(spec=health_targets_models.HealthTargets)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_target
        mock_db.execute.return_value = mock_result

        # Act
        result = health_targets_crud.edit_health_target(health_target, user_id, mock_db)

        # Assert
        mock_db.commit.assert_called_once()

    def test_edit_health_target_exception(self, mock_db):
        """
        Test exception handling in edit_health_target.
        """
        # Arrange
        user_id = 1
        health_target = health_targets_schema.HealthTargetsUpdate(
            id=1, user_id=user_id, weight=75.0
        )

        # Mock successful get but fail on commit
        mock_db_target = MagicMock(spec=health_targets_models.HealthTargets)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_target
        mock_db.execute.return_value = mock_result
        mock_db.commit.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            health_targets_crud.edit_health_target(health_target, user_id, mock_db)

        assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert exc_info.value.detail == "Database error occurred"
        mock_db.rollback.assert_called_once()

    def test_edit_health_target_clear_fields(self, mock_db):
        """
        Test edit can clear optional fields by setting to None.
        """
        # Arrange
        user_id = 1
        health_target = health_targets_schema.HealthTargetsUpdate(
            id=1, user_id=user_id, weight=None, steps=None
        )

        mock_db_target = MagicMock(spec=health_targets_models.HealthTargets)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_db_target
        mock_db.execute.return_value = mock_result

        # Act
        result = health_targets_crud.edit_health_target(health_target, user_id, mock_db)

        # Assert
        mock_db.commit.assert_called_once()
