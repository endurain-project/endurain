import uuid
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
        update = health_targets_schema.HealthTargetsUpdate(weight_kg=75.0)
        mock_edit.return_value = MagicMock()

        result = health_targets_service.update_health_targets(update, 1, mock_db, if_match="*")

        assert result is mock_edit.return_value
        mock_edit.assert_called_once_with(update, 1, mock_db, if_match="*")
        mock_db.commit.assert_called_once()


class TestRestoreProfileRecords:
    @patch("modules.health.health_targets.service.health_targets_crud.edit_health_targets")
    def test_edits_the_targets_the_account_has_with_the_editable_fields_only(self, mock_edit, mock_db):
        rows = [{"id": str(uuid.uuid4()), "user_id": 999, "version": 4, "weight_kg": 80.0, "steps": 10000}]

        assert health_targets_service.restore_profile_records(rows, 1, {}, mock_db) == 1

        target, user_id, db = mock_edit.call_args.args
        assert (user_id, db) == (1, mock_db)
        assert (target.weight_kg, target.steps) == (80.0, 10000)
        assert mock_edit.call_args.kwargs == {"if_match": "*"}

    @patch("modules.health.health_targets.service.health_targets_crud.edit_health_targets")
    def test_an_archive_with_the_names_from_before_the_units_is_read(self, mock_edit, mock_db):
        rows = [{"weight": 80.0, "sleep": 28800, "fasting": 57600, "steps": 10000}]

        assert health_targets_service.restore_profile_records(rows, 1, {}, mock_db) == 1

        target = mock_edit.call_args.args[0]
        assert (target.weight_kg, target.sleep_seconds, target.fasting_seconds) == (80.0, 28800, 57600)

    @patch("modules.health.health_targets.service.health_targets_crud.edit_health_targets")
    def test_numbers_archived_as_strings_are_read_as_numbers(self, mock_edit, mock_db):
        rows = [{"weight_kg": "80.5", "steps": "10000", "sleep_seconds": "28800"}]

        assert health_targets_service.restore_profile_records(rows, 1, {}, mock_db) == 1

        target = mock_edit.call_args.args[0]
        assert (target.weight_kg, target.steps, target.sleep_seconds) == (80.5, 10000, 28800)

    @patch("modules.health.health_targets.service.health_targets_crud.edit_health_targets")
    def test_a_number_that_cannot_be_read_is_left_out_and_the_rest_staged(self, mock_edit, mock_db):
        rows = [{"weight_kg": "bad", "steps": "wrong", "sleep_seconds": "nope"}]

        assert health_targets_service.restore_profile_records(rows, 1, {}, mock_db) == 1

        target = mock_edit.call_args.args[0]
        assert (target.weight_kg, target.steps, target.sleep_seconds) == (None, None, None)

    @patch("modules.health.health_targets.service.health_targets_crud.edit_health_targets")
    def test_an_archive_without_targets_stages_nothing(self, mock_edit, mock_db):
        assert health_targets_service.restore_profile_records([], 1, {}, mock_db) == 0
        mock_edit.assert_not_called()
