from datetime import date as datetime_date
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm.exc import StaleDataError

import core.date_range as core_date_range
import core.exceptions as core_exceptions
import modules.health.constants as health_constants
import modules.health.health_weight.schema as health_weight_schema
import modules.health.health_weight.service as health_weight_service

_PREFIX = "modules.health.health_weight.service"

_NO_RANGE = core_date_range.DateRange()


def _user(height):
    return MagicMock(height=height)


@pytest.fixture(autouse=True)
def _known_user():
    """Give the user a height, as every manual write derives its BMI from it, and a local today."""
    with (
        patch(f"{_PREFIX}.users_integration.get_user", return_value=_user(175)),
        patch(f"{_PREFIX}.users_integration.local_today", return_value=datetime_date(2024, 1, 15)),
    ):
        yield


class TestStageCreate:
    @patch(f"{_PREFIX}.health_weight_crud.create_health_weight")
    @patch(f"{_PREFIX}.users_integration.get_user", return_value=_user(175))
    def test_derives_bmi_from_user_height(self, _get_user, mock_create, mock_db):
        record = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight_kg=75.0)

        health_weight_service.stage_create_health_weight(1, record, mock_db)

        stored = mock_create.call_args.args[1]
        assert stored.bmi == pytest.approx(75.0 / 1.75**2)
        mock_db.commit.assert_not_called()

    @patch(f"{_PREFIX}.health_weight_crud.create_health_weight")
    @patch(f"{_PREFIX}.users_integration.get_user", return_value=_user(70))
    def test_bmi_is_none_when_the_height_gives_an_out_of_range_value(self, _get_user, mock_create, mock_db):
        record = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight_kg=80.0)

        health_weight_service.stage_create_health_weight(1, record, mock_db)

        stored = mock_create.call_args.args[1]
        assert stored.bmi is None
        health_weight_schema.HealthWeightRead.model_validate(
            {**stored.model_dump(), "id": 1, "user_id": 1, "version": 1}
        )

    @patch(f"{_PREFIX}.health_weight_crud.create_health_weight")
    @patch(f"{_PREFIX}.users_integration.get_user", return_value=None)
    def test_bmi_is_none_for_unknown_user(self, _get_user, mock_create, mock_db):
        record = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight_kg=75.0)

        health_weight_service.stage_create_health_weight(1, record, mock_db)

        assert mock_create.call_args.args[1].bmi is None

    @patch(f"{_PREFIX}.health_weight_crud.create_health_weight")
    def test_ignores_a_given_bmi(self, mock_create, mock_db):
        record = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight_kg=75.0, bmi=22.0)

        health_weight_service.stage_create_health_weight(1, record, mock_db)

        assert mock_create.call_args.args[1].bmi == pytest.approx(75.0 / 1.75**2)


class TestStageEdit:
    @patch(f"{_PREFIX}.health_weight_crud.edit_health_weight")
    @patch(f"{_PREFIX}.users_integration.get_user", return_value=_user(180))
    def test_derives_bmi_when_weight_changes(self, _get_user, mock_edit, mock_db):
        record = health_weight_schema.HealthWeightUpdate(date=datetime_date(2024, 1, 15), weight_kg=81.0)

        health_weight_service.stage_edit_health_weight(1, 7, record, mock_db, if_match="*")

        assert mock_edit.call_args.args[2].bmi == pytest.approx(81.0 / 1.8**2)


class TestCreateHealthWeight:
    @patch(f"{_PREFIX}.health_weight_crud.create_health_weight")
    @patch(f"{_PREFIX}.health_weight_crud.get_health_weight_by_date_and_user_id", return_value=None)
    def test_creates_and_commits_when_the_date_is_free(self, _get_by_date, mock_create, mock_db):
        record = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight_kg=75.0, bmi=22.0)

        result = health_weight_service.create_health_weight(1, record, mock_db)

        assert result is mock_create.return_value
        mock_db.commit.assert_called_once()

    @patch(f"{_PREFIX}.health_weight_crud.edit_health_weight")
    @patch(f"{_PREFIX}.health_weight_crud.create_health_weight", side_effect=core_exceptions.ConflictError("duplicate"))
    def test_a_date_that_already_has_a_record_is_a_conflict(self, _create, mock_edit, mock_db):
        record = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight_kg=72.0, bmi=22.0)

        with pytest.raises(core_exceptions.ConflictError):
            health_weight_service.create_health_weight(1, record, mock_db)

        mock_edit.assert_not_called()
        mock_db.commit.assert_not_called()


class TestUpsertHealthWeight:
    @patch(f"{_PREFIX}.health_weight_crud.edit_health_weight")
    @patch(f"{_PREFIX}.health_weight_crud.get_health_weight_by_date_and_user_id")
    def test_a_writer_that_changed_the_row_first_is_retried_against_its_version(
        self, mock_get_by_date, mock_edit, mock_db
    ):
        mock_get_by_date.return_value = MagicMock(id=7)
        mock_edit.side_effect = [StaleDataError("moved"), "stored"]
        record = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight_kg=72.0, bmi=22.0)

        result = health_weight_service.stage_upsert_health_weight(1, record, mock_db)

        assert result == "stored"
        assert mock_edit.call_count == 2

    @patch(f"{_PREFIX}.health_weight_crud.edit_health_weight", side_effect=StaleDataError("moved"))
    @patch(f"{_PREFIX}.health_weight_crud.get_health_weight_by_date_and_user_id")
    def test_a_row_that_keeps_moving_is_given_up_on(self, mock_get_by_date, mock_edit, mock_db):
        mock_get_by_date.return_value = MagicMock(id=7)
        record = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight_kg=72.0, bmi=22.0)

        with pytest.raises(StaleDataError):
            health_weight_service.stage_upsert_health_weight(1, record, mock_db)

        assert mock_edit.call_count == health_constants.UPSERT_ATTEMPTS

    @patch(f"{_PREFIX}.health_weight_crud.edit_health_weight")
    @patch(f"{_PREFIX}.health_weight_crud.get_health_weight_by_date_and_user_id")
    def test_updates_the_existing_record_of_the_date(self, mock_get_by_date, mock_edit, mock_db):
        mock_get_by_date.return_value = MagicMock(id=7)
        record = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight_kg=75.0, bmi=22.0)

        health_weight_service.stage_upsert_health_weight(1, record, mock_db)

        assert mock_edit.call_args.args[:2] == (1, 7)
        assert mock_edit.call_args.args[2].date == datetime_date(2024, 1, 15)
        mock_db.commit.assert_not_called()


class TestEditAndDelete:
    @patch(f"{_PREFIX}.health_weight_crud.edit_health_weight")
    def test_edit_commits(self, mock_edit, mock_db):
        record = health_weight_schema.HealthWeightUpdate(date=datetime_date(2024, 1, 15), weight_kg=75.0, bmi=22.0)

        health_weight_service.edit_health_weight(1, 7, record, mock_db, if_match="*")

        mock_db.commit.assert_called_once()

    @patch(f"{_PREFIX}.health_weight_crud.delete_health_weight")
    def test_delete_commits(self, mock_delete, mock_db):
        health_weight_service.delete_health_weight(1, 5, mock_db, if_match="*")

        mock_delete.assert_called_once_with(1, 5, mock_db, if_match="*")
        mock_db.commit.assert_called_once()


class TestListHealthWeight:
    @patch(f"{_PREFIX}.health_weight_crud.get_health_weight_by_user_id", return_value=[])
    @patch(f"{_PREFIX}.health_weight_crud.get_health_weight_number_by_user_id", return_value=0)
    @patch(f"{_PREFIX}.users_integration.local_today", return_value=datetime_date(2024, 1, 15))
    def test_resolves_the_interval_in_the_users_calendar(self, _today, mock_number, mock_list, mock_db):
        result = health_weight_service.list_health_weight(
            1,
            mock_db,
            page_number=2,
            num_records=10,
            interval=health_constants.Interval.LAST_30_DAYS,
            date_range=_NO_RANGE,
        )

        since = datetime_date(2023, 12, 16)
        mock_number.assert_called_once_with(1, mock_db, since, None)
        mock_list.assert_called_once_with(1, mock_db, 2, 10, since, None)
        assert (result.total, result.page, result.num_records) == (0, 2, 10)

    @patch(f"{_PREFIX}.health_weight_crud.get_health_weight_by_user_id", return_value=[])
    @patch(f"{_PREFIX}.health_weight_crud.get_health_weight_number_by_user_id", return_value=0)
    def test_no_interval_means_no_lower_bound(self, mock_number, mock_list, mock_db):
        health_weight_service.list_health_weight(1, mock_db, date_range=_NO_RANGE)

        mock_number.assert_called_once_with(1, mock_db, None, None)


class TestMissingDate:
    @patch(f"{_PREFIX}.health_weight_crud.create_health_weight")
    @patch(f"{_PREFIX}.health_weight_crud.get_health_weight_by_date_and_user_id", return_value=None)
    @patch(f"{_PREFIX}.users_integration.local_today", return_value=datetime_date(2024, 1, 15))
    def test_defaults_to_the_athletes_local_today(self, mock_today, _get_by_date, mock_create, mock_db):
        record = health_weight_schema.HealthWeightCreate(weight_kg=75.0, bmi=22.0)

        health_weight_service.create_health_weight(1, record, mock_db)

        assert mock_create.call_args.args[1].date == datetime_date(2024, 1, 15)
        mock_today.assert_called_once_with(1, mock_db)


class TestFutureDate:
    @patch(f"{_PREFIX}.health_weight_crud.create_health_weight")
    @patch(f"{_PREFIX}.users_integration.local_today", return_value=datetime_date(2024, 1, 15))
    def test_create_refuses_a_date_after_the_local_today(self, _today, mock_create, mock_db):
        record = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 16), weight_kg=75.0)

        with pytest.raises(core_exceptions.InvalidInputError):
            health_weight_service.create_health_weight(1, record, mock_db)

        mock_create.assert_not_called()

    @patch(f"{_PREFIX}.health_weight_crud.create_health_weight")
    @patch(f"{_PREFIX}.users_integration.local_today", return_value=datetime_date(2024, 1, 15))
    def test_create_accepts_the_local_today(self, _today, mock_create, mock_db):
        record = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight_kg=75.0)

        health_weight_service.create_health_weight(1, record, mock_db)

        mock_create.assert_called_once()

    @patch(f"{_PREFIX}.health_weight_crud.edit_health_weight")
    @patch(f"{_PREFIX}.users_integration.local_today", return_value=datetime_date(2024, 1, 15))
    def test_edit_refuses_a_date_after_the_local_today(self, _today, mock_edit, mock_db):
        update = health_weight_schema.HealthWeightUpdate(date=datetime_date(2024, 1, 16))

        with pytest.raises(core_exceptions.InvalidInputError):
            health_weight_service.edit_health_weight(1, 5, update, mock_db, if_match="1")

        mock_edit.assert_not_called()


class TestRestoreProfileRecords:
    @patch(f"{_PREFIX}.stage_upsert_health_weight")
    def test_stages_each_row_without_the_row_identity(self, mock_upsert, mock_db):
        rows = [{"id": 9, "user_id": 999, "version": 4, "date": "2024-01-15", "weight_kg": 75.5}]

        assert health_weight_service.restore_profile_records(rows, 1, {}, mock_db) == 1

        user_id, record, db = mock_upsert.call_args.args
        assert (user_id, db) == (1, mock_db)
        assert record.weight_kg == 75.5

    @patch(f"{_PREFIX}.stage_upsert_health_weight")
    def test_numbers_archived_as_strings_are_read_as_numbers(self, mock_upsert, mock_db):
        rows = [
            {"date": "2024-01-15", "weight_kg": "75.5", "bmi": "24.1", "physique_rating": "5", "metabolic_age": "30"}
        ]

        assert health_weight_service.restore_profile_records(rows, 1, {}, mock_db) == 1

        record = mock_upsert.call_args.args[1]
        assert (record.weight_kg, record.bmi, record.physique_rating, record.metabolic_age) == (75.5, 24.1, 5, 30)

    @patch(f"{_PREFIX}.stage_upsert_health_weight")
    def test_a_number_that_cannot_be_read_leaves_a_record_that_is_skipped(self, mock_upsert, mock_db):
        rows = [{"weight_kg": "abc", "physique_rating": "xyz", "metabolic_age": "invalid"}]

        assert health_weight_service.restore_profile_records(rows, 1, {}, mock_db) == 0
        mock_upsert.assert_not_called()

    @patch(f"{_PREFIX}.stage_upsert_health_weight")
    def test_no_rows_stages_nothing(self, mock_upsert, mock_db):
        assert health_weight_service.restore_profile_records([], 1, {}, mock_db) == 0
        mock_upsert.assert_not_called()
