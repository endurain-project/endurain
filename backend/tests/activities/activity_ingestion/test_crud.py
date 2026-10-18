"""Tests for activity upload job persistence."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from tests._helpers.models import mock_model

import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.crud as ingestion_crud
import modules.activities.activity_ingestion.models as activity_ingestion_models
import modules.activities.activity_ingestion.schema as activity_ingestion_schema

_NOW = datetime(2026, 7, 28, 10, 0, 0, tzinfo=UTC)
_KIND = activity_ingestion_constants.IngestionJobKind.UPLOAD

# Captured before any test patches the module attribute, so ``_row`` keeps
# speccing against the real class rather than the patch's MagicMock.
_MODEL = activity_ingestion_models.ActivityIngestionJob


def _row(**overrides):
    defaults = {
        "id": "job-1",
        "user_id": 7,
        "kind": "upload",
        "filename": "ride.gpx",
        "staged_key": "abc.gpx",
        "provider": None,
        "import_source": None,
        "files_total": None,
        "files_done": None,
        "files_failed": None,
        "status": "pending",
        "error_code": None,
        "activity_ids": None,
        "created_at": _NOW,
        "updated_at": _NOW,
        "completed_at": None,
    }
    return mock_model(_MODEL, **{**defaults, **overrides})


def _stub_first(mock_db, row):
    """Stub the ``db.scalars(stmt).first()`` path this CRUD uses."""
    mock_db.scalars.return_value.first.return_value = row


class TestCreateUploadJob:
    @patch("modules.activities.activity_ingestion.crud.activity_ingestion_models.ActivityIngestionJob")
    def test_stages_without_committing(self, model, mock_db):
        """Lets the row and its outbox event land in one transaction."""
        model.return_value = _row()
        result = ingestion_crud.create_ingestion_job(
            "job-1", 7, _KIND, mock_db, filename="ride.gpx", staged_key="abc.gpx"
        )
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()
        assert result.id == "job-1"
        assert result.status == activity_ingestion_constants.IngestionJobStatus.PENDING


class TestGetUploadJob:
    def test_returns_the_job(self, mock_db):
        _stub_first(mock_db, _row())
        result = ingestion_crud.get_ingestion_job("job-1", 7, mock_db)
        assert result is not None
        assert result.id == "job-1"

    def test_returns_none_when_absent(self, mock_db):
        _stub_first(mock_db, None)
        assert ingestion_crud.get_ingestion_job("job-1", 7, mock_db) is None

    def test_filters_by_owner(self, mock_db):
        """The owner is part of the query, not an afterthought in the caller."""
        _stub_first(mock_db, None)
        ingestion_crud.get_ingestion_job("job-1", 7, mock_db)
        stmt = mock_db.scalars.call_args.args[0]
        # Read the clause structure rather than compiling to SQL: compiling
        # would configure every mapper, which makes this test depend on what
        # else the run happened to import.
        filtered = {clause.left.name for clause in stmt.whereclause.get_children()}
        assert filtered == {"id", "user_id"}

    def test_maps_a_completed_job(self, mock_db):
        _stub_first(mock_db, _row(status="completed", activity_ids=[11, 12], completed_at=_NOW))
        result = ingestion_crud.get_ingestion_job("job-1", 7, mock_db)
        assert result is not None
        assert result.status == activity_ingestion_constants.IngestionJobStatus.COMPLETED
        assert result.activity_ids == [11, 12]

    def test_maps_a_failed_job(self, mock_db):
        _stub_first(mock_db, _row(status="failed", error_code="invalid_file"))
        result = ingestion_crud.get_ingestion_job("job-1", 7, mock_db)
        assert result is not None
        assert result.error_code == activity_ingestion_constants.IngestionJobErrorCode.INVALID_FILE


class TestGetJobWorkItem:
    def test_returns_the_stored_owner_and_key(self, mock_db):
        """The owner comes from the row, so a tampered event cannot reattribute the import."""
        mock_db.get.return_value = _row()
        assert ingestion_crud.get_job_work_item("job-1", mock_db) == (7, "abc.gpx")

    def test_returns_none_when_already_consumed(self, mock_db):
        mock_db.get.return_value = _row(staged_key=None)
        assert ingestion_crud.get_job_work_item("job-1", mock_db) is None

    def test_returns_none_for_an_unknown_job(self, mock_db):
        mock_db.get.return_value = None
        assert ingestion_crud.get_job_work_item("job-1", mock_db) is None


class TestTerminalTransitions:
    def test_mark_completed_records_ids_and_clears_the_staged_key(self, mock_db):
        row = _row(status="processing")
        mock_db.get.return_value = row
        ingestion_crud.mark_completed("job-1", [11], mock_db)
        assert row.status == "completed"
        assert row.activity_ids == [11]
        # Cleared so a retry after success is a no-op rather than a re-import.
        assert row.staged_key is None
        assert row.completed_at is not None
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_mark_failed_records_only_the_sanitized_code(self, mock_db):
        row = _row(status="processing")
        mock_db.get.return_value = row
        ingestion_crud.mark_failed("job-1", activity_ingestion_constants.IngestionJobErrorCode.INVALID_FILE, mock_db)
        assert row.status == "failed"
        assert row.error_code == "invalid_file"
        assert row.staged_key is None

    def test_mark_processing_is_one_conditional_update(self, mock_db):
        mock_db.execute.return_value.rowcount = 1
        claimed = ingestion_crud.mark_processing("job-1", mock_db, lease=timedelta(0))
        assert claimed is True
        mock_db.execute.assert_called_once()
        mock_db.flush.assert_called_once()

    def test_mark_processing_reports_a_lost_claim(self, mock_db):
        mock_db.execute.return_value.rowcount = 0
        assert ingestion_crud.mark_processing("job-1", mock_db, lease=timedelta(0)) is False

    def test_transitions_on_a_missing_row_are_no_ops(self, mock_db):
        mock_db.get.return_value = None
        ingestion_crud.mark_completed("gone", [1], mock_db)
        ingestion_crud.mark_failed("gone", activity_ingestion_constants.IngestionJobErrorCode.INVALID_FILE, mock_db)
        mock_db.commit.assert_not_called()


class TestDeleteJobsBefore:
    def test_deletes_only_terminal_rows(self, mock_db):
        mock_db.execute.return_value.rowcount = 2
        assert ingestion_crud.delete_jobs_before(_NOW, mock_db) == 2
        compiled = str(mock_db.execute.call_args.args[0].compile())
        assert compiled.startswith("DELETE FROM activity_ingestion_jobs")
        assert "completed_at IS NOT NULL" in compiled
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_returns_zero_when_nothing_is_stale(self, mock_db):
        mock_db.execute.return_value.rowcount = 0
        assert ingestion_crud.delete_jobs_before(_NOW, mock_db) == 0


class TestTerminalJobsAreNotOverwritten:
    def test_a_late_writer_cannot_overwrite_a_finished_job(self, mock_db):
        row = _row(completed_at=_NOW)
        mock_db.get.return_value = row
        ingestion_crud.mark_completed("job-1", [1], mock_db)
        ingestion_crud.mark_failed("job-1", activity_ingestion_constants.IngestionJobErrorCode.INVALID_FILE, mock_db)
        assert row.completed_at == _NOW
        mock_db.flush.assert_not_called()

    def test_the_row_is_read_under_a_lock(self, mock_db):
        mock_db.get.return_value = _row()
        ingestion_crud.mark_completed("job-1", [1], mock_db)
        assert mock_db.get.call_args.kwargs["with_for_update"] is True


class TestSchemaMapping:
    def test_ids_default_to_an_empty_list_not_null(self, mock_db):
        """The client always gets a list to iterate."""
        _stub_first(mock_db, _row(activity_ids=None))
        result = ingestion_crud.get_ingestion_job("job-1", 7, mock_db)
        assert result is not None
        assert result.activity_ids == []

    def test_the_staged_key_is_not_part_of_the_read_schema(self):
        """It is an internal filesystem detail and must not reach a client."""
        assert "staged_key" not in activity_ingestion_schema.ActivityIngestionJobRead.model_fields
