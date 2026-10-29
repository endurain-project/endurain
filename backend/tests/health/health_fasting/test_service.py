from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm.exc import StaleDataError

import core.exceptions as core_exceptions
import modules.health.constants as health_constants
import modules.health.health_fasting.schema as health_fasting_schema
import modules.health.health_fasting.service as health_fasting_service

_PREFIX = "modules.health.health_fasting.service"
_CRUD = f"{_PREFIX}.health_fasting_crud"


def _complete(status: str = "completed", notes: str | None = None) -> health_fasting_schema.HealthFastingComplete:
    return health_fasting_schema.HealthFastingComplete(
        fast_end_time=datetime(2024, 1, 16, 8, 0, 0, tzinfo=UTC), status=status, notes=notes
    )


class TestGetHealthFasting:
    @patch(f"{_CRUD}.get_health_fasting_by_id_and_user_id")
    def test_returns_the_record(self, mock_get, mock_db):
        assert health_fasting_service.get_health_fasting(1, 5, mock_db) is mock_get.return_value
        mock_get.assert_called_once_with(5, 1, mock_db)

    @patch(f"{_CRUD}.get_health_fasting_by_id_and_user_id", return_value=None)
    def test_missing_record_is_not_found(self, _get, mock_db):
        with pytest.raises(core_exceptions.NotFoundError, match="Fasting record not found"):
            health_fasting_service.get_health_fasting(1, 5, mock_db)


class TestCreateHealthFasting:
    @patch(f"{_CRUD}.create_health_fasting")
    @patch(f"{_CRUD}.get_active_fasting_by_user_id", return_value=None)
    def test_starts_a_fast_and_commits(self, _active, mock_create, mock_db):
        record = health_fasting_schema.HealthFastingCreate(fast_start_time=datetime(2024, 1, 15, 8, 0, 0))

        assert health_fasting_service.create_health_fasting(1, record, mock_db) is mock_create.return_value
        mock_db.commit.assert_called_once()

    @patch(f"{_CRUD}.create_health_fasting")
    @patch(f"{_CRUD}.get_active_fasting_by_user_id")
    def test_refuses_a_second_active_fast(self, _active, mock_create, mock_db):
        record = health_fasting_schema.HealthFastingCreate(fast_start_time=datetime(2024, 1, 15, 8, 0, 0))

        with pytest.raises(core_exceptions.ConflictError, match="already has an active fasting session"):
            health_fasting_service.create_health_fasting(1, record, mock_db)

        mock_create.assert_not_called()
        mock_db.commit.assert_not_called()


class TestEditAndDelete:
    @patch(f"{_CRUD}.edit_health_fasting")
    def test_edit_commits(self, _edit, mock_db):
        health_fasting_service.edit_health_fasting(
            1, 7, health_fasting_schema.HealthFastingUpdate(), mock_db, if_match="*"
        )

        mock_db.commit.assert_called_once()

    @patch(f"{_CRUD}.delete_health_fasting")
    def test_delete_commits(self, mock_delete, mock_db):
        health_fasting_service.delete_health_fasting(1, 5, mock_db, if_match="*")

        mock_delete.assert_called_once_with(1, 5, mock_db, if_match="*")
        mock_db.commit.assert_called_once()


class TestCompleteHealthFasting:
    @patch(f"{_CRUD}.end_health_fasting")
    @patch(f"{_CRUD}.get_health_fasting_by_id_and_user_id")
    def test_derives_the_duration_and_commits(self, mock_get, mock_end, mock_db):
        mock_get.return_value = MagicMock(status="in_progress", fast_start_time=datetime(2024, 1, 15, 8, 0, 0))

        health_fasting_service.complete_health_fasting(1, 5, _complete(notes="done"), mock_db, if_match="*")

        args = mock_end.call_args.args
        assert args[:2] == (1, 5)
        assert args[2] == datetime(2024, 1, 16, 8, 0, 0, tzinfo=UTC)
        assert args[3:6] == ("completed", 86400, "done")
        mock_db.commit.assert_called_once()

    @patch("modules.health.record_crud.exists", return_value=True)
    @patch(f"{_CRUD}.end_health_fasting", side_effect=StaleDataError())
    @patch(f"{_CRUD}.get_health_fasting_by_id_and_user_id")
    def test_a_session_changed_by_another_request_is_a_stale_write_not_a_server_error(
        self, mock_get, mock_end, _exists, mock_db
    ):
        mock_get.return_value = MagicMock(status="in_progress", fast_start_time=datetime(2024, 1, 15, 8, 0, 0))

        with pytest.raises(core_exceptions.PreconditionFailedError):
            health_fasting_service.complete_health_fasting(1, 5, _complete(), mock_db, if_match='"1"')

        mock_db.commit.assert_not_called()

    @patch(f"{_CRUD}.end_health_fasting")
    @patch(f"{_CRUD}.get_health_fasting_by_id_and_user_id")
    def test_refuses_a_session_that_is_not_in_progress(self, mock_get, mock_end, mock_db):
        mock_get.return_value = MagicMock(status="completed", fast_start_time=datetime(2024, 1, 15, 8, 0, 0))

        with pytest.raises(core_exceptions.ConflictError, match="not in progress"):
            health_fasting_service.complete_health_fasting(1, 5, _complete(), mock_db, if_match="*")

        mock_end.assert_not_called()
        mock_db.commit.assert_not_called()

    @patch(f"{_CRUD}.end_health_fasting")
    @patch(f"{_CRUD}.get_health_fasting_by_id_and_user_id")
    def test_refuses_an_end_before_the_start(self, mock_get, mock_end, mock_db):
        mock_get.return_value = MagicMock(status="in_progress", fast_start_time=datetime(2024, 1, 17, 8, 0, 0))

        with pytest.raises(core_exceptions.InvalidInputError, match="before it started"):
            health_fasting_service.complete_health_fasting(1, 5, _complete(), mock_db, if_match="*")

        mock_end.assert_not_called()
        mock_db.commit.assert_not_called()

    @patch(f"{_CRUD}.get_health_fasting_by_id_and_user_id", return_value=None)
    def test_unknown_session_is_not_found(self, _get, mock_db):
        with pytest.raises(core_exceptions.NotFoundError):
            health_fasting_service.complete_health_fasting(1, 5, _complete(), mock_db, if_match="*")

    @patch(f"{_CRUD}.end_health_fasting")
    @patch(f"{_CRUD}.get_health_fasting_by_id_and_user_id")
    def test_status_defaults_to_completed(self, mock_get, mock_end, mock_db):
        mock_get.return_value = MagicMock(status="in_progress", fast_start_time=datetime(2024, 1, 15, 8, 0, 0))
        complete = health_fasting_schema.HealthFastingComplete(fast_end_time=datetime(2024, 1, 16, 8, 0, 0, tzinfo=UTC))

        health_fasting_service.complete_health_fasting(1, 5, complete, mock_db, if_match="*")

        assert mock_end.call_args.args[3] == "completed"


class TestGetFastingStats:
    @patch(f"{_PREFIX}.users_integration.local_today", return_value=date(2024, 1, 15))
    @patch(f"{_PREFIX}.users_integration.resolve_timezone", return_value="UTC")
    def test_combines_the_aggregates_streaks_and_completion_rate(self, _tz, _today, mock_db):
        with (
            patch(f"{_CRUD}.get_completed_fasting_count", return_value=3),
            patch(f"{_CRUD}.get_health_fasting_number_by_user_id", return_value=4),
            patch(f"{_CRUD}.get_avg_fasting_duration", return_value=50000),
            patch(f"{_CRUD}.get_total_fasting_seconds", return_value=150000),
            patch(
                f"{_CRUD}.get_completed_fasting_dates_by_user_id",
                return_value=[date(2024, 1, 13), date(2024, 1, 14), date(2024, 1, 15)],
            ),
        ):
            stats = health_fasting_service.get_fasting_stats(1, mock_db)

        assert (stats.total_fasts, stats.current_streak, stats.longest_streak) == (3, 3, 3)
        assert (stats.avg_duration_seconds, stats.total_fasting_seconds) == (50000, 150000)
        assert stats.completion_rate == 75.0

    @patch(f"{_PREFIX}.users_integration.local_today", return_value=date(2024, 1, 15))
    @patch(f"{_PREFIX}.users_integration.resolve_timezone", return_value="UTC")
    def test_completion_rate_is_zero_without_any_fast(self, _tz, _today, mock_db):
        with (
            patch(f"{_CRUD}.get_completed_fasting_count", return_value=0),
            patch(f"{_CRUD}.get_health_fasting_number_by_user_id", return_value=0),
            patch(f"{_CRUD}.get_avg_fasting_duration", return_value=None),
            patch(f"{_CRUD}.get_total_fasting_seconds", return_value=0),
            patch(f"{_CRUD}.get_completed_fasting_dates_by_user_id", return_value=[]),
        ):
            stats = health_fasting_service.get_fasting_stats(1, mock_db)

        assert (stats.completion_rate, stats.current_streak, stats.longest_streak) == (0.0, 0, 0)


class TestListHealthFasting:
    @patch(f"{_CRUD}.get_health_fasting_by_user_id", return_value=[])
    @patch(f"{_CRUD}.get_health_fasting_number_by_user_id", return_value=0)
    @patch(f"{_PREFIX}.users_integration.local_today", return_value=date(2024, 1, 15))
    def test_resolves_the_interval_in_the_users_calendar(self, _today, mock_number, mock_list, mock_db):
        result = health_fasting_service.list_health_fasting(
            1, mock_db, page_number=2, num_records=10, interval=health_constants.Interval.LAST_30_DAYS
        )

        since = date(2023, 12, 16)
        mock_number.assert_called_once_with(1, mock_db, since)
        mock_list.assert_called_once_with(1, mock_db, 2, 10, since)
        assert (result.total, result.page, result.num_records) == (0, 2, 10)

    @patch(f"{_CRUD}.get_health_fasting_by_user_id", return_value=[])
    @patch(f"{_CRUD}.get_health_fasting_number_by_user_id", return_value=0)
    def test_no_interval_means_no_lower_bound(self, mock_number, mock_list, mock_db):
        health_fasting_service.list_health_fasting(1, mock_db)

        mock_number.assert_called_once_with(1, mock_db, None)


class TestStageImportHealthFasting:
    def _record(self) -> health_fasting_schema.HealthFastingCreate:
        return health_fasting_schema.HealthFastingCreate(
            fast_start_time=datetime(2024, 1, 15, 20, 0, tzinfo=UTC), status="completed"
        )

    @patch(f"{_CRUD}.create_health_fasting")
    @patch(f"{_CRUD}.health_fasting_exists_at", return_value=False)
    def test_stages_a_session_the_user_does_not_have(self, _exists, mock_create, mock_db):
        record = self._record()

        assert health_fasting_service.stage_import_health_fasting(1, record, mock_db) is True

        mock_create.assert_called_once_with(1, record, mock_db)
        mock_db.commit.assert_not_called()

    @patch(f"{_CRUD}.create_health_fasting")
    @patch(f"{_CRUD}.health_fasting_exists_at", return_value=True)
    def test_skips_a_session_already_started_at_that_time(self, _exists, mock_create, mock_db):
        assert health_fasting_service.stage_import_health_fasting(1, self._record(), mock_db) is False

        mock_create.assert_not_called()

    @patch(f"{_CRUD}.create_health_fasting", side_effect=core_exceptions.ConflictError("active"))
    @patch(f"{_CRUD}.health_fasting_exists_at", return_value=False)
    def test_skips_a_running_fast_when_the_user_already_has_one(self, _exists, _create, mock_db):
        assert health_fasting_service.stage_import_health_fasting(1, self._record(), mock_db) is False
