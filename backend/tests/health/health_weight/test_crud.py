from datetime import date as datetime_date
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.health.health_weight.crud as health_weight_crud
import modules.health.health_weight.models as health_weight_models
import modules.health.health_weight.schema as health_weight_schema


def _row(record_id: int = 1, user_id: int = 1, weight: float = 75.0) -> MagicMock:
    row = MagicMock(spec=health_weight_models.HealthWeight)
    row.id = record_id
    row.version = 1
    row.user_id = user_id
    row.date = datetime_date(2024, 1, 15)
    row.weight = weight
    for column in (
        "bmi",
        "body_fat",
        "body_water",
        "bone_mass",
        "muscle_mass",
        "physique_rating",
        "visceral_fat",
        "metabolic_age",
        "source",
    ):
        setattr(row, column, None)
    return row


def _returns_scalars(mock_db, rows):
    mock_db.execute.return_value.scalars.return_value.all.return_value = rows


def _returns_one(mock_db, row):
    mock_db.execute.return_value.scalar_one_or_none.return_value = row


class TestListReads:
    def test_get_all_health_weight(self, mock_db):
        _returns_scalars(mock_db, [_row(1), _row(2)])

        result = health_weight_crud.get_all_health_weight(mock_db)

        assert [r.id for r in result] == [1, 2]
        mock_db.execute.assert_called_once()

    def test_get_all_health_weight_by_user_id_empty(self, mock_db):
        _returns_scalars(mock_db, [])

        assert health_weight_crud.get_all_health_weight_by_user_id(1, mock_db) == []

    def test_get_health_weight_by_user_id_paginates_and_bounds(self, mock_db):
        _returns_scalars(mock_db, [_row()])

        result = health_weight_crud.get_health_weight_by_user_id(1, mock_db, 2, 10, datetime_date(2024, 1, 1))

        assert len(result) == 1
        compiled = str(mock_db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))
        assert "LIMIT 10 OFFSET 10" in compiled
        assert "health_weight.date >=" in compiled

    def test_number_counts(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 3

        assert health_weight_crud.get_health_weight_number_by_user_id(1, mock_db) == 3

    def test_number_with_a_lower_bound(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 1

        health_weight_crud.get_health_weight_number_by_user_id(1, mock_db, datetime_date(2024, 1, 1))

        assert "health_weight.date >=" in str(mock_db.execute.call_args.args[0])


class TestSingleReads:
    def test_by_date_found(self, mock_db):
        _returns_one(mock_db, _row())

        assert health_weight_crud.get_health_weight_by_date_and_user_id(1, "2024-01-15", mock_db).id == 1

    def test_by_date_not_found(self, mock_db):
        _returns_one(mock_db, None)

        assert health_weight_crud.get_health_weight_by_date_and_user_id(1, "2024-01-15", mock_db) is None

    def test_latest_found(self, mock_db):
        _returns_one(mock_db, _row(5))

        assert health_weight_crud.get_latest_weight_by_user_id(1, mock_db).id == 5

    def test_latest_not_found(self, mock_db):
        _returns_one(mock_db, None)

        assert health_weight_crud.get_latest_weight_by_user_id(1, mock_db) is None


class TestCreateHealthWeight:
    def test_stages_without_committing(self, mock_db, stub_model):
        record = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight=75.0, bmi=22.0)

        with stub_model(health_weight_crud, _row()) as model:
            health_weight_crud.create_health_weight(1, record, mock_db)

        assert model.call_args.kwargs["user_id"] == 1
        assert model.call_args.kwargs["bmi"] == 22.0
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_duplicate_date_is_a_conflict(self, mock_db, stub_model):
        mock_db.flush.side_effect = IntegrityError("duplicate", None, None)
        record = health_weight_schema.HealthWeightCreate(date=datetime_date(2024, 1, 15), weight=75.0)

        with (
            stub_model(health_weight_crud, _row()),
            pytest.raises(core_exceptions.ConflictError, match="Duplicate entry error"),
        ):
            health_weight_crud.create_health_weight(1, record, mock_db)


class TestEditHealthWeight:
    def test_updates_the_given_fields_and_stages(self, mock_db):
        row = _row()
        _returns_one(mock_db, row)
        update = health_weight_schema.HealthWeightUpdate(date=datetime_date(2024, 1, 15), weight=80.0)

        health_weight_crud.edit_health_weight(1, 1, update, mock_db, if_match="*")

        assert row.weight == 80.0
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_unknown_record_is_not_found(self, mock_db):
        _returns_one(mock_db, None)
        update = health_weight_schema.HealthWeightUpdate(date=datetime_date(2024, 1, 15), weight=80.0)

        with pytest.raises(core_exceptions.NotFoundError, match="Health weight not found"):
            health_weight_crud.edit_health_weight(1, 9, update, mock_db, if_match="*")


class TestDeleteHealthWeight:
    def test_deletes_and_stages(self, mock_db):
        row = _row()
        _returns_one(mock_db, row)

        health_weight_crud.delete_health_weight(1, 1, mock_db, if_match="*")

        mock_db.delete.assert_called_once_with(row)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_unknown_record_is_not_found(self, mock_db):
        _returns_one(mock_db, None)

        with pytest.raises(core_exceptions.NotFoundError):
            health_weight_crud.delete_health_weight(1, 9, mock_db, if_match="*")
        mock_db.delete.assert_not_called()


class TestRecalculateBmiForUser:
    @pytest.mark.parametrize("height", [175.0, None, 0.0])
    def test_issues_one_bulk_update_and_stages(self, mock_db, height):
        health_weight_crud.recalculate_bmi_for_user(1, height, mock_db)

        mock_db.execute.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()
