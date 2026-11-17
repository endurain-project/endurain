import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from tests._helpers.db import setup_mock_execute
from tests._helpers.models import mock_model

_ACTIVITY_ID = uuid.UUID("00000000-0000-4000-8000-000000000005")

_T0 = datetime(2024, 1, 15, 8, 0, tzinfo=UTC)


class TestCreateActivityLaps:
    @patch("modules.activities.activity_laps.crud.activity_laps_models.ActivityLaps")
    def test_success(self, mock_laps_model, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_laps_model.return_value = MagicMock()
        laps = [{"lap_number": 1, "lap_time": 3600.0}]
        crud.create_activity_laps(laps, _ACTIVITY_ID, mock_db)
        mock_db.add_all.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_empty(self, mock_db):
        import modules.activities.activity_laps.crud as crud

        crud.create_activity_laps([], _ACTIVITY_ID, mock_db)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()


class TestGetActivityLaps:
    """Persistence only — the access decision lives in ``activity_laps.service``."""

    @patch("modules.activities.activity_laps.serializers.to_read_schema")
    def test_success(self, mock_to_read, mock_db):
        import modules.activities.activity_laps.crud as crud
        import modules.activities.activity_laps.models as m

        mock_to_read.return_value = MagicMock()
        setup_mock_execute(
            mock_db, return_scalars_all=[mock_model(m.ActivityLaps, id=uuid.uuid4(), activity_id=_ACTIVITY_ID)]
        )
        r = crud.get_activity_laps(activity_id=_ACTIVITY_ID, db=mock_db)
        assert len(r) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity_laps.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert crud.get_activity_laps(activity_id=_ACTIVITY_ID, db=mock_db) == []


class TestGetActivitiesLaps:
    """The batch read no longer joins the parent: it is handed scoped ids."""

    @patch("modules.activities.activity_laps.serializers.to_read_schema")
    def test_success(self, mock_to_read, mock_db):
        import modules.activities.activity_laps.crud as crud
        import modules.activities.activity_laps.models as m

        mock_to_read.return_value = MagicMock()
        mock_db.scalars.return_value.all.return_value = [
            MagicMock(spec=m.ActivityLaps, id=uuid.uuid4(), activity_id=_ACTIVITY_ID)
        ]

        assert len(crud.get_activities_laps(activity_ids=[_ACTIVITY_ID], db=mock_db)) == 1

    def test_empty_ids_short_circuits(self, mock_db):
        import modules.activities.activity_laps.crud as crud

        assert crud.get_activities_laps(activity_ids=[], db=mock_db) == []
        mock_db.scalars.assert_not_called()

    def test_no_rows(self, mock_db):
        import modules.activities.activity_laps.crud as crud

        mock_db.scalars.return_value.all.return_value = []

        assert crud.get_activities_laps(activity_ids=[_ACTIVITY_ID], db=mock_db) == []


def _ids(*numbers):
    return [uuid.UUID(int=n) for n in numbers]


class TestOrdering:
    """Rows come back by their natural key; the id only breaks a tie."""

    def _row(self, row_id, key):
        import modules.activities.activity_laps.models as m

        return m.ActivityLaps(id=row_id, activity_id=_ACTIVITY_ID, start_time=key)

    def _read(self, rows, **page):
        from tests._helpers.db import create_sqlite_session

        import modules.activities.activity_laps.crud as crud

        db = create_sqlite_session()
        try:
            for row in rows:
                db.add(row)
            db.commit()
            return [(r.start_time, r.id) for r in crud.get_activity_laps(_ACTIVITY_ID, db, **page)]
        finally:
            db.close()

    def test_rows_inserted_out_of_order_come_back_by_start_time(self):
        a, b, c = _ids(3, 1, 2)
        rows = [self._row(a, _T0 + timedelta(minutes=2)), self._row(b, _T0), self._row(c, _T0 + timedelta(minutes=1))]

        assert [row_id for _, row_id in self._read(rows)] == [b, c, a]

    def test_a_tie_breaks_by_id(self):
        high, low = _ids(9, 4)
        rows = [self._row(high, _T0), self._row(low, _T0)]

        assert [row_id for _, row_id in self._read(rows)] == [low, high]

    def test_paging_follows_the_same_order(self):
        a, b, c = _ids(3, 1, 2)
        rows = [self._row(a, _T0 + timedelta(minutes=2)), self._row(b, _T0), self._row(c, _T0 + timedelta(minutes=1))]

        assert [row_id for _, row_id in self._read(rows, page_number=2, num_records=2)] == [a]
