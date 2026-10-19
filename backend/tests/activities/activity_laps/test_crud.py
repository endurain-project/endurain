from unittest.mock import MagicMock, patch

from tests._helpers.db import setup_mock_execute
from tests._helpers.models import mock_model


class TestCreateActivityLaps:
    @patch("modules.activities.activity_laps.crud.activity_laps_models.ActivityLaps")
    def test_success(self, mock_laps_model, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_laps_model.return_value = MagicMock()
        laps = [{"lap_number": 1, "lap_time": 3600.0}]
        crud.create_activity_laps(laps, 1, mock_db)
        mock_db.add_all.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_empty(self, mock_db):
        import modules.activities.activity_laps.crud as crud

        crud.create_activity_laps([], 1, mock_db)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()


class TestGetActivityLaps:
    """Persistence only — the access decision lives in ``activity_laps.service``."""

    @patch("modules.activities.activity_laps.serializers.to_read_schema")
    def test_success(self, mock_to_read, mock_db):
        import modules.activities.activity_laps.crud as crud
        import modules.activities.activity_laps.models as m

        mock_to_read.return_value = MagicMock()
        setup_mock_execute(mock_db, return_scalars_all=[mock_model(m.ActivityLaps, id=1, activity_id=1)])
        r = crud.get_activity_laps(activity_id=1, db=mock_db)
        assert len(r) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity_laps.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert crud.get_activity_laps(activity_id=1, db=mock_db) == []


class TestGetActivitiesLaps:
    """The batch read no longer joins the parent: it is handed scoped ids."""

    @patch("modules.activities.activity_laps.serializers.to_read_schema")
    def test_success(self, mock_to_read, mock_db):
        import modules.activities.activity_laps.crud as crud
        import modules.activities.activity_laps.models as m

        mock_to_read.return_value = MagicMock()
        mock_db.scalars.return_value.all.return_value = [MagicMock(spec=m.ActivityLaps, id=1, activity_id=1)]

        assert len(crud.get_activities_laps(activity_ids=[1], db=mock_db)) == 1

    def test_empty_ids_short_circuits(self, mock_db):
        import modules.activities.activity_laps.crud as crud

        assert crud.get_activities_laps(activity_ids=[], db=mock_db) == []
        mock_db.scalars.assert_not_called()

    def test_no_rows(self, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_db.scalars.return_value.all.return_value = []

        assert crud.get_activities_laps(activity_ids=[1], db=mock_db) == []
