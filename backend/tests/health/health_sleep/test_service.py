from datetime import date as datetime_date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm.exc import StaleDataError

import core.exceptions as core_exceptions
import modules.health.constants as health_constants
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_sleep.service as health_sleep_service
import modules.health.health_sleep.sleep_scoring as health_sleep_sleep_scoring

_PREFIX = "modules.health.health_sleep.service"
_SCORING = f"{_PREFIX}.health_sleep_sleep_scoring.calculate_and_set_sleep_scores"


def _update() -> health_sleep_schema.HealthSleepUpdate:
    return health_sleep_schema.HealthSleepUpdate(date=datetime_date(2024, 1, 15), total_sleep_seconds=28800)


class TestStageEdit:
    @patch(_SCORING)
    @patch(f"{_PREFIX}.health_sleep_crud.edit_health_sleep")
    def test_stages_without_scoring_or_committing(self, mock_edit, mock_scoring, mock_db):
        record = _update()

        health_sleep_service.stage_edit_health_sleep(1, 7, record, mock_db, if_match="*")

        mock_edit.assert_called_once_with(1, 7, record, mock_db, if_match="*")
        mock_scoring.assert_not_called()
        mock_db.commit.assert_not_called()


class TestCreateHealthSleep:
    @patch(_SCORING)
    @patch(f"{_PREFIX}.health_sleep_crud.create_health_sleep")
    @patch(f"{_PREFIX}.health_sleep_crud.get_health_sleep_by_date_and_user_id", return_value=None)
    def test_scores_creates_and_commits_when_the_date_is_free(self, _get_by_date, mock_create, mock_scoring, mock_db):
        record = health_sleep_schema.HealthSleepCreate(date=datetime_date(2024, 1, 15), total_sleep_seconds=28800)

        result = health_sleep_service.create_health_sleep(1, record, mock_db)

        mock_scoring.assert_called_once_with(record)
        assert result is mock_create.return_value
        mock_db.commit.assert_called_once()

    @patch(_SCORING)
    @patch(f"{_PREFIX}.health_sleep_crud.edit_health_sleep")
    @patch(f"{_PREFIX}.health_sleep_crud.create_health_sleep", side_effect=core_exceptions.ConflictError("duplicate"))
    def test_a_date_that_already_has_a_record_is_a_conflict(self, _create, mock_edit, _scoring, mock_db):
        record = health_sleep_schema.HealthSleepCreate(date=datetime_date(2024, 1, 15), total_sleep_seconds=28800)

        with pytest.raises(core_exceptions.ConflictError):
            health_sleep_service.create_health_sleep(1, record, mock_db)

        mock_edit.assert_not_called()
        mock_db.commit.assert_not_called()


class TestUpsertHealthSleep:
    @patch(f"{_PREFIX}.health_sleep_crud.edit_health_sleep")
    @patch(f"{_PREFIX}.health_sleep_crud.get_health_sleep_by_date_and_user_id")
    def test_a_writer_that_changed_the_row_first_is_retried_against_its_version(
        self, mock_get_by_date, mock_edit, mock_db
    ):
        mock_get_by_date.return_value = MagicMock(id=7)
        mock_edit.side_effect = [StaleDataError("moved"), "stored"]
        record = health_sleep_schema.HealthSleepCreate(date=datetime_date(2024, 1, 15), total_sleep_seconds=28800)

        result = health_sleep_service.stage_upsert_health_sleep(1, record, mock_db)

        assert result == "stored"
        assert mock_edit.call_count == 2

    @patch(f"{_PREFIX}.health_sleep_crud.edit_health_sleep", side_effect=StaleDataError("moved"))
    @patch(f"{_PREFIX}.health_sleep_crud.get_health_sleep_by_date_and_user_id")
    def test_a_row_that_keeps_moving_is_given_up_on(self, mock_get_by_date, mock_edit, mock_db):
        mock_get_by_date.return_value = MagicMock(id=7)
        record = health_sleep_schema.HealthSleepCreate(date=datetime_date(2024, 1, 15), total_sleep_seconds=28800)

        with pytest.raises(StaleDataError):
            health_sleep_service.stage_upsert_health_sleep(1, record, mock_db)

        assert mock_edit.call_count == health_constants.UPSERT_ATTEMPTS

    @patch(_SCORING)
    @patch(f"{_PREFIX}.health_sleep_crud.edit_health_sleep")
    @patch(f"{_PREFIX}.health_sleep_crud.get_health_sleep_by_date_and_user_id")
    def test_updates_the_existing_record_of_the_date(self, mock_get_by_date, mock_edit, _scoring, mock_db):
        mock_get_by_date.return_value = MagicMock(id=7)
        record = health_sleep_schema.HealthSleepCreate(date=datetime_date(2024, 1, 15), total_sleep_seconds=28800)

        health_sleep_service.stage_upsert_health_sleep(1, record, mock_db)

        assert mock_edit.call_args.args[:2] == (1, 7)
        assert mock_edit.call_args.args[2].date == datetime_date(2024, 1, 15)
        mock_db.commit.assert_not_called()


def _stored() -> health_sleep_schema.HealthSleepRead:
    """A stored record whose scores came from a full set of inputs."""
    return health_sleep_schema.HealthSleepRead(
        id=7,
        user_id=1,
        date=datetime_date(2024, 1, 15),
        total_sleep_seconds=28800,
        deep_sleep_seconds=5184,
        light_sleep_seconds=14400,
        rem_sleep_seconds=6480,
        awake_sleep_seconds=720,
        awake_count=0,
        restless_moments_count=0,
        avg_sleep_stress=20,
        sleep_score_overall=95,
        sleep_score_duration="EXCELLENT",
        sleep_score_quality="EXCELLENT",
        awake_count_score="EXCELLENT",
        rem_percentage_score="GOOD",
        deep_percentage_score="GOOD",
        light_percentage_score="GOOD",
        sleep_stress_score="EXCELLENT",
    )


def _edit_and_capture(mock_db, patch_body: dict) -> health_sleep_schema.HealthSleepUpdate:
    """Run the service edit on ``_stored()`` and return the update that reached the crud."""
    update = health_sleep_schema.HealthSleepUpdate(**patch_body)
    with (
        patch(f"{_PREFIX}.health_sleep_crud.get_health_sleep_by_id", return_value=_stored()),
        patch(f"{_PREFIX}.health_sleep_crud.edit_health_sleep") as mock_edit,
    ):
        health_sleep_service.edit_health_sleep(1, 7, update, mock_db, if_match="*")
    return mock_edit.call_args.args[2]


class TestEditAndDelete:
    def test_edit_commits(self, mock_db):
        _edit_and_capture(mock_db, {"awake_count": 2})

        mock_db.commit.assert_called_once()

    def test_edit_scores_the_merged_record_not_the_partial_body(self, mock_db):
        sent = _edit_and_capture(mock_db, {"awake_count": 2})

        expected = _stored().model_copy(update={"awake_count": 2})
        health_sleep_sleep_scoring.calculate_and_set_sleep_scores(expected)
        for field in health_sleep_sleep_scoring.SCORE_FIELDS:
            assert getattr(sent, field) == getattr(expected, field), field
        assert sent.sleep_score_duration == "EXCELLENT"
        assert sent.awake_count_score == "GOOD"

    def test_edit_without_a_scoring_input_leaves_every_score_alone(self, mock_db):
        sent = _edit_and_capture(mock_db, {"resting_heart_rate": 50})

        assert sent.model_fields_set == {"resting_heart_rate"}

    def test_edit_ignores_scores_the_client_sends(self, mock_db):
        sent = _edit_and_capture(mock_db, {"awake_count": 2, "sleep_score_overall": 1})

        assert sent.sleep_score_overall != 1

    def test_edit_of_a_missing_record_is_not_found(self, mock_db):
        with (
            patch(
                f"{_PREFIX}.health_sleep_crud.get_health_sleep_by_id", side_effect=core_exceptions.NotFoundError("gone")
            ),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            health_sleep_service.edit_health_sleep(1, 7, _update(), mock_db, if_match="*")

        mock_db.commit.assert_not_called()

    @patch(f"{_PREFIX}.health_sleep_crud.delete_health_sleep")
    def test_delete_commits(self, mock_delete, mock_db):
        health_sleep_service.delete_health_sleep(1, 5, mock_db, if_match="*")

        mock_delete.assert_called_once_with(1, 5, mock_db, if_match="*")
        mock_db.commit.assert_called_once()


class TestListHealthSleep:
    @patch(f"{_PREFIX}.health_sleep_crud.get_health_sleep_by_user_id", return_value=[])
    @patch(f"{_PREFIX}.health_sleep_crud.get_health_sleep_number_by_user_id", return_value=0)
    @patch(f"{_PREFIX}.users_integration.local_today", return_value=datetime_date(2024, 1, 15))
    def test_resolves_the_interval_in_the_users_calendar(self, _today, mock_number, mock_list, mock_db):
        result = health_sleep_service.list_health_sleep(
            1, mock_db, page_number=2, num_records=10, interval=health_constants.Interval.LAST_30_DAYS
        )

        since = datetime_date(2023, 12, 16)
        mock_number.assert_called_once_with(1, mock_db, since)
        mock_list.assert_called_once_with(1, mock_db, 2, 10, since)
        assert (result.total, result.page, result.num_records) == (0, 2, 10)

    @patch(f"{_PREFIX}.health_sleep_crud.get_health_sleep_by_user_id", return_value=[])
    @patch(f"{_PREFIX}.health_sleep_crud.get_health_sleep_number_by_user_id", return_value=0)
    def test_no_interval_means_no_lower_bound(self, mock_number, mock_list, mock_db):
        health_sleep_service.list_health_sleep(1, mock_db)

        mock_number.assert_called_once_with(1, mock_db, None)


class TestMissingDate:
    @patch(_SCORING)
    @patch(f"{_PREFIX}.health_sleep_crud.create_health_sleep")
    @patch(f"{_PREFIX}.health_sleep_crud.get_health_sleep_by_date_and_user_id", return_value=None)
    @patch(f"{_PREFIX}.users_integration.local_today", return_value=datetime_date(2024, 1, 15))
    def test_defaults_to_the_athletes_local_today(self, mock_today, _get_by_date, mock_create, _scoring, mock_db):
        record = health_sleep_schema.HealthSleepCreate(total_sleep_seconds=28800)

        health_sleep_service.create_health_sleep(1, record, mock_db)

        assert mock_create.call_args.args[1].date == datetime_date(2024, 1, 15)
        mock_today.assert_called_once_with(1, mock_db)
