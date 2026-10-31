from unittest.mock import MagicMock, patch

import modules.health.health_targets.schema as health_targets_schema
import modules.health.health_targets.service as health_targets_service


class TestGetHealthTargets:
    @patch("modules.health.health_targets.service.health_targets_crud.get_health_targets_by_user_id")
    def test_returns_crud_result(self, mock_get, mock_db):
        mock_get.return_value = None

        assert health_targets_service.get_health_targets(1, mock_db) is None
        mock_get.assert_called_once_with(1, mock_db)


class TestUpdateHealthTargets:
    @patch("modules.health.health_targets.service.health_targets_crud.edit_health_targets")
    def test_commits_after_edit(self, mock_edit, mock_db):
        update = health_targets_schema.HealthTargetsUpdate(weight=75.0)
        mock_edit.return_value = MagicMock()

        result = health_targets_service.update_health_targets(update, 1, mock_db, if_match="*")

        assert result is mock_edit.return_value
        mock_edit.assert_called_once_with(update, 1, mock_db, if_match="*")
        mock_db.commit.assert_called_once()
