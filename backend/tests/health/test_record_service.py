from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm.exc import StaleDataError

import core.exceptions as core_exceptions
import modules.health.constants as health_constants
import modules.health.health_steps.crud as health_steps_crud
import modules.health.health_steps.schema as health_steps_schema
import modules.health.record_service as health_record_service
import modules.health.schema as health_schema

_EXISTS = "modules.health.record_crud.exists"


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

        series = health_record_service.chart(1, health_constants.Interval.LAST_30_DAYS, fetch, mock_db)

        fetch.assert_called_once_with(date(2026, 3, 1), health_constants.ChartBucket.DAY)
        assert series == health_schema.HealthChartSeries(bucket=health_constants.ChartBucket.DAY, points=[point])


class TestListPage:
    @patch("modules.users.users.integration_service.local_today", return_value=date(2026, 3, 31))
    def test_counts_and_fetches_from_the_interval_start(self, _today, mock_db):
        count = MagicMock(return_value=5)
        fetch = MagicMock(return_value=["a", "b"])

        page = health_record_service.list_page(1, health_constants.Interval.LAST_30_DAYS, 1, 2, count, fetch, mock_db)

        count.assert_called_once_with(date(2026, 3, 1))
        fetch.assert_called_once_with(date(2026, 3, 1))
        assert page.total == 5
        assert page.items == ["a", "b"]

    def test_no_interval_is_unbounded(self, mock_db):
        count = MagicMock(return_value=0)
        fetch = MagicMock(return_value=[])

        health_record_service.list_page(1, None, 1, 2, count, fetch, mock_db)

        count.assert_called_once_with(None)
        fetch.assert_called_once_with(None)


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
        find = MagicMock(return_value=MagicMock(id=7))
        create = MagicMock()
        edit = MagicMock(return_value="edited")

        result = health_record_service.upsert_dated(
            1, record, health_steps_schema.HealthStepsUpdate, find, create, edit, mock_db
        )

        assert result == "edited"
        create.assert_not_called()
        record_id, update = edit.call_args.args
        assert record_id == 7
        assert isinstance(update, health_steps_schema.HealthStepsUpdate)
        assert update.steps == 10
