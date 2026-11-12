import uuid
from datetime import date
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm.exc import StaleDataError

import core.date_range as core_date_range
import core.exceptions as core_exceptions
import modules.health.constants as health_constants
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_steps.crud as health_steps_crud
import modules.health.health_steps.schema as health_steps_schema
import modules.health.record_service as health_record_service
import modules.health.schema as health_schema

_EXISTS = "modules.health.record_crud.exists"
_NO_RANGE = core_date_range.DateRange()
_RECORD_ID = uuid.uuid4()


class TestCommitWrite:
    def test_commits_and_returns_what_the_write_staged(self, mock_db):
        result = health_record_service.commit_write(
            health_steps_crud.SPEC, 1, 2, lambda: "staged", mock_db, log_message="Edited a steps record"
        )

        assert result == "staged"
        mock_db.commit.assert_called_once()

    @patch(_EXISTS, return_value=True)
    def test_a_write_that_lost_the_version_race_is_a_precondition_failure(self, mock_exists, mock_db):
        mock_db.commit.side_effect = StaleDataError()

        with pytest.raises(core_exceptions.PreconditionFailedError, match="steps record"):
            health_record_service.commit_write(health_steps_crud.SPEC, 1, 2, lambda: None, mock_db, log_message="x")

        mock_db.rollback.assert_called_once()
        mock_exists.assert_called_once_with(health_steps_crud.SPEC, 1, 2, mock_db)

    @patch(_EXISTS, return_value=False)
    def test_a_record_deleted_meanwhile_is_not_found_with_the_spec_message(self, _exists, mock_db):
        mock_db.commit.side_effect = StaleDataError()

        with pytest.raises(core_exceptions.NotFoundError, match="Health steps not found"):
            health_record_service.commit_write(health_steps_crud.SPEC, 1, 2, lambda: None, mock_db, log_message="x")


class TestChart:
    @patch("modules.users.users.integration_service.local_today", return_value=date(2026, 3, 31))
    def test_fetches_from_the_interval_start_in_the_finest_bucket(self, _today, mock_db):
        point = health_schema.HealthChartPoint(date=date(2026, 3, 30), value=1)
        fetch = MagicMock(return_value=[point])

        series = health_record_service.chart(1, health_constants.Interval.LAST_30_DAYS, _NO_RANGE, fetch, mock_db)

        fetch.assert_called_once_with(date(2026, 3, 1), None, health_constants.ChartBucket.DAY)
        assert series == health_schema.HealthChartSeries(bucket=health_constants.ChartBucket.DAY, points=[point])


class TestListPage:
    @patch("modules.users.users.integration_service.local_today", return_value=date(2026, 3, 31))
    def test_counts_and_fetches_from_the_interval_start(self, _today, mock_db):
        count = MagicMock(return_value=5)
        fetch = MagicMock(return_value=["a", "b"])

        page = health_record_service.list_page(
            1, health_constants.Interval.LAST_30_DAYS, _NO_RANGE, 1, 2, count, fetch, mock_db
        )

        count.assert_called_once_with(date(2026, 3, 1), None)
        fetch.assert_called_once_with(date(2026, 3, 1), None)
        assert page.total == 5
        assert page.items == ["a", "b"]

    def test_no_interval_is_unbounded(self, mock_db):
        count = MagicMock(return_value=0)
        fetch = MagicMock(return_value=[])

        health_record_service.list_page(1, None, _NO_RANGE, 1, 2, count, fetch, mock_db)

        count.assert_called_once_with(None, None)
        fetch.assert_called_once_with(None, None)


class TestUpsertDated:
    @patch("modules.users.users.integration_service.local_today", return_value=date(2026, 3, 31))
    def test_a_missing_date_becomes_the_users_local_today(self, _today, mock_db):
        record = health_steps_schema.HealthStepsCreate(steps=10)
        find = MagicMock(return_value=None)
        create = MagicMock(return_value="created")
        edit = MagicMock()

        result = health_record_service.upsert_dated(
            1, record, health_steps_schema.HealthStepsUpdate, find, create, edit, mock_db
        )

        assert result == "created"
        assert record.date == date(2026, 3, 31)
        find.assert_called_with("2026-03-31")
        create.assert_called_once_with(record)
        edit.assert_not_called()

    def test_an_existing_day_is_edited_not_created(self, mock_db):
        record = health_steps_schema.HealthStepsCreate(steps=10, date=date(2026, 3, 30))
        find = MagicMock(return_value=MagicMock(id=_RECORD_ID))
        create = MagicMock()
        edit = MagicMock(return_value="edited")

        result = health_record_service.upsert_dated(
            1, record, health_steps_schema.HealthStepsUpdate, find, create, edit, mock_db
        )

        assert result == "edited"
        create.assert_not_called()
        record_id, update = edit.call_args.args
        assert record_id == _RECORD_ID
        assert isinstance(update, health_steps_schema.HealthStepsUpdate)
        assert update.steps == 10


class TestRestoreArchivedRecords:
    _IDENTITY: ClassVar[dict[str, int | uuid.UUID]] = {"id": uuid.uuid4(), "user_id": 999, "version": 4}

    @staticmethod
    def _restore(rows, stage, **kwargs):
        return health_record_service.restore_archived_records(
            rows, health_steps_schema.HealthStepsCreate, stage, 1, MagicMock(), kind="health_steps", **kwargs
        )

    def test_stages_each_row_without_the_row_identity(self):
        stage = MagicMock(return_value=True)

        count = self._restore([{"date": "2024-01-15", "steps": 9000, **self._IDENTITY}], stage)

        assert count == 1
        user_id, record, _ = stage.call_args.args
        assert user_id == 1
        assert record.steps == 9000

    def test_a_value_the_server_derives_is_dropped_from_an_archived_row(self):
        stage = MagicMock(return_value=True)
        row = {"fast_start_time": "2024-01-15T20:00:00Z", "actual_duration_seconds": 57600, "status": "completed"}
        restore = lambda derived: health_record_service.restore_archived_records(  # noqa: E731
            [row],
            health_fasting_schema.HealthFastingCreate,
            stage,
            1,
            MagicMock(),
            kind="health_fasting",
            server_derived=derived,
        )

        assert restore(frozenset()) == 0
        assert restore(frozenset({"actual_duration_seconds"})) == 1
        stage.assert_called_once()

    def test_a_skipped_duplicate_is_not_counted(self):
        stage = MagicMock(return_value=False)

        assert self._restore([{"date": "2024-01-15", "steps": 5}], stage) == 0

    def test_a_stage_that_returns_a_record_counts(self):
        stage = MagicMock(return_value=MagicMock())

        assert self._restore([{"date": "2024-01-15", "steps": 5}], stage) == 1

    def test_an_invalid_row_is_skipped_and_the_rest_staged(self):
        stage = MagicMock(return_value=True)

        count = self._restore([{"steps": "many"}, {"unknown": 1}, {"date": "2024-01-16", "steps": 100}], stage)

        assert count == 1
        stage.assert_called_once()

    def test_no_rows_stages_nothing(self):
        stage = MagicMock(return_value=True)

        assert self._restore([], stage) == 0
        stage.assert_not_called()

    def test_an_error_from_the_stage_is_not_swallowed(self):
        stage = MagicMock(side_effect=core_exceptions.ConflictError("boom"))

        with pytest.raises(core_exceptions.ConflictError):
            self._restore([{"date": "2024-01-15", "steps": 5}], stage)


class TestGetRecord:
    @patch("modules.health.record_crud.get_owned")
    def test_returns_the_owned_row_as_its_read_schema(self, mock_get_owned, mock_db):
        mock_get_owned.return_value = MagicMock(
            id=_RECORD_ID, user_id=2, date=date(2024, 1, 15), steps=900, version=4, source="manual"
        )

        record = health_record_service.get_record(health_steps_crud.SPEC, _RECORD_ID, 2, mock_db)

        assert (record.id, record.steps, record.version) == (_RECORD_ID, 900, 4)
        mock_get_owned.assert_called_once_with(health_steps_crud.SPEC, _RECORD_ID, 2, mock_db)

    @patch("modules.health.record_crud.get_owned", side_effect=core_exceptions.NotFoundError("Health steps not found"))
    def test_a_record_of_another_user_is_not_found(self, _get_owned, mock_db):
        with pytest.raises(core_exceptions.NotFoundError, match="Health steps not found"):
            health_record_service.get_record(health_steps_crud.SPEC, _RECORD_ID, 2, mock_db)
