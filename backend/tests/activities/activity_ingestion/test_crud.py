"""Tests for activity upload job persistence."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.models import mock_model

import core.job_status as core_job_status
import modules.activities.activity_ingestion.constants as activity_ingestion_constants
import modules.activities.activity_ingestion.crud as ingestion_crud
import modules.activities.activity_ingestion.models as activity_ingestion_models
import modules.activities.activity_ingestion.schema as activity_ingestion_schema

_JOB_1 = uuid.UUID("00000000-0000-4000-8000-0000000000a1")

_ID_A = uuid.UUID("00000000-0000-4000-8000-00000000000a")
_ID_B = uuid.UUID("00000000-0000-4000-8000-00000000000b")

_NOW = datetime(2026, 7, 28, 10, 0, 0, tzinfo=UTC)
_KIND = activity_ingestion_constants.IngestionJobKind.UPLOAD

# Captured before any test patches the module attribute, so ``_row`` keeps
# speccing against the real class rather than the patch's MagicMock.
_MODEL = activity_ingestion_models.ActivityIngestionJob


def _row(**overrides):
    defaults = {
        "id": _JOB_1,
        "user_id": MOCK_USER_ID,
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
            _JOB_1, MOCK_USER_ID, _KIND, mock_db, filename="ride.gpx", staged_key="abc.gpx"
        )
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()
        assert result.id == _JOB_1
        assert result.status == core_job_status.JobState.QUEUED


class TestGetUploadJob:
    def test_returns_the_job(self, mock_db):
        _stub_first(mock_db, _row())
        result = ingestion_crud.get_ingestion_job(_JOB_1, MOCK_USER_ID, mock_db)
        assert result is not None
        assert result.id == _JOB_1

    def test_returns_none_when_absent(self, mock_db):
        _stub_first(mock_db, None)
        assert ingestion_crud.get_ingestion_job(_JOB_1, MOCK_USER_ID, mock_db) is None

    def test_filters_by_owner(self, mock_db):
        """The owner is part of the query, not an afterthought in the caller."""
        _stub_first(mock_db, None)
        ingestion_crud.get_ingestion_job(_JOB_1, MOCK_USER_ID, mock_db)
        stmt = mock_db.scalars.call_args.args[0]
        # Read the clause structure rather than compiling to SQL: compiling
        # would configure every mapper, which makes this test depend on what
        # else the run happened to import.
        filtered = {clause.left.name for clause in stmt.whereclause.get_children()}
        assert filtered == {"id", "user_id"}

    def test_maps_a_completed_job(self, mock_db):
        _stub_first(mock_db, _row(status="completed", activity_ids=[str(_ID_A), str(_ID_B)], completed_at=_NOW))
        result = ingestion_crud.get_ingestion_job(_JOB_1, MOCK_USER_ID, mock_db)
        assert result is not None
        assert result.status == core_job_status.JobState.SUCCEEDED
        assert result.activity_ids == [_ID_A, _ID_B]

    def test_maps_a_failed_job(self, mock_db):
        _stub_first(mock_db, _row(status="failed", error_code="invalid_file"))
        result = ingestion_crud.get_ingestion_job(_JOB_1, MOCK_USER_ID, mock_db)
        assert result is not None
        assert result.error_code == activity_ingestion_constants.IngestionJobErrorCode.INVALID_FILE


class TestGetJobWorkItem:
    def test_returns_the_stored_owner_and_key(self, mock_db):
        """The owner comes from the row, so a tampered event cannot reattribute the import."""
        mock_db.get.return_value = _row()
        assert ingestion_crud.get_job_work_item(_JOB_1, mock_db) == (MOCK_USER_ID, "abc.gpx")

    def test_returns_none_when_already_consumed(self, mock_db):
        mock_db.get.return_value = _row(staged_key=None)
        assert ingestion_crud.get_job_work_item(_JOB_1, mock_db) is None

    def test_returns_none_for_an_unknown_job(self, mock_db):
        mock_db.get.return_value = None
        assert ingestion_crud.get_job_work_item(_JOB_1, mock_db) is None


class TestTerminalTransitions:
    def test_mark_completed_records_ids_and_clears_the_staged_key(self, mock_db):
        row = _row(status="processing")
        mock_db.get.return_value = row
        ingestion_crud.mark_completed(_JOB_1, [_ID_A], mock_db)
        assert row.status == "completed"
        assert row.activity_ids == [str(_ID_A)]
        # Cleared so a retry after success is a no-op rather than a re-import.
        assert row.staged_key is None
        assert row.completed_at is not None
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_mark_failed_records_only_the_sanitized_code(self, mock_db):
        row = _row(status="processing")
        mock_db.get.return_value = row
        ingestion_crud.mark_failed(_JOB_1, activity_ingestion_constants.IngestionJobErrorCode.INVALID_FILE, mock_db)
        assert row.status == "failed"
        assert row.error_code == "invalid_file"
        assert row.staged_key is None

    def test_mark_failed_reports_the_owner_and_kind_so_they_can_be_told(self, mock_db):
        mock_db.get.return_value = _row(status="processing", user_id=MOCK_USER_ID)

        failed = ingestion_crud.mark_failed(
            _JOB_1, activity_ingestion_constants.IngestionJobErrorCode.INVALID_FILE, mock_db
        )

        assert failed == (MOCK_USER_ID, activity_ingestion_constants.IngestionJobKind.UPLOAD)

    def test_mark_failed_reports_nobody_for_a_job_that_is_missing_or_already_terminal(self, mock_db):
        code = activity_ingestion_constants.IngestionJobErrorCode.INVALID_FILE
        mock_db.get.return_value = None
        assert ingestion_crud.mark_failed("gone", code, mock_db) is None

        mock_db.get.return_value = _row(status="completed", completed_at=datetime.now(UTC))
        assert ingestion_crud.mark_failed("done", code, mock_db) is None

    def test_mark_processing_is_one_conditional_update(self, mock_db):
        mock_db.execute.return_value.rowcount = 1
        claimed = ingestion_crud.mark_processing(_JOB_1, mock_db, lease=timedelta(0))
        assert claimed is True
        mock_db.execute.assert_called_once()
        mock_db.flush.assert_called_once()

    def test_mark_processing_reports_a_lost_claim(self, mock_db):
        mock_db.execute.return_value.rowcount = 0
        assert ingestion_crud.mark_processing(_JOB_1, mock_db, lease=timedelta(0)) is False

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
        ingestion_crud.mark_completed(_JOB_1, [1], mock_db)
        ingestion_crud.mark_failed(_JOB_1, activity_ingestion_constants.IngestionJobErrorCode.INVALID_FILE, mock_db)
        assert row.completed_at == _NOW
        mock_db.flush.assert_not_called()

    def test_the_row_is_read_under_a_lock(self, mock_db):
        mock_db.get.return_value = _row()
        ingestion_crud.mark_completed(_JOB_1, [1], mock_db)
        assert mock_db.get.call_args.kwargs["with_for_update"] is True


class TestSchemaMapping:
    def test_ids_default_to_an_empty_list_not_null(self, mock_db):
        """The client always gets a list to iterate."""
        _stub_first(mock_db, _row(activity_ids=None))
        result = ingestion_crud.get_ingestion_job(_JOB_1, MOCK_USER_ID, mock_db)
        assert result is not None
        assert result.activity_ids == []

    def test_the_staged_key_is_not_part_of_the_read_schema(self):
        """It is an internal filesystem detail and must not reach a client."""
        assert "staged_key" not in activity_ingestion_schema.ActivityIngestionJobRead.model_fields


class TestActivityIdsRoundTrip:
    def test_a_completed_jobs_activity_ids_round_trip_as_uuid_strings(self, mock_db):
        row = _row(status="processing")
        mock_db.get.return_value = row
        ingestion_crud.mark_completed(_JOB_1, [_ID_A, _ID_B], mock_db)
        assert row.activity_ids == [str(_ID_A), str(_ID_B)]

        row.completed_at = _NOW
        _stub_first(mock_db, row)
        result = ingestion_crud.get_ingestion_job(_JOB_1, MOCK_USER_ID, mock_db)
        assert result is not None
        assert result.activity_ids == [_ID_A, _ID_B]
