import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from tests._helpers.db import setup_mock_execute
from tests._helpers.models import mock_model

_ACTIVITY_ID = uuid.UUID("00000000-0000-4000-8000-000000000005")

_T0 = datetime(2024, 1, 15, 8, 0, tzinfo=UTC)


class TestCreateActivitySets:
    @patch("modules.activities.activity_sets.crud.activity_sets_models.ActivitySets")
    def test_success(self, mock_sets_model, mock_db):
        import modules.activities.activity_sets.crud as crud
        from modules.activities.activity_sets.contracts import ActivitySetsCreate

        mock_sets_model.return_value = MagicMock()
        sets = [
            ActivitySetsCreate(
                activity_id=_ACTIVITY_ID, duration=300.0, set_type="interval", start_time="2024-01-15T08:00:00"
            )
        ]
        crud.create_activity_sets(sets, _ACTIVITY_ID, mock_db)
        mock_db.add_all.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_empty(self, mock_db):
        import modules.activities.activity_sets.crud as crud

        crud.create_activity_sets([], _ACTIVITY_ID, mock_db)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()


class TestGetActivitySets:
    """Persistence only — the access decision lives in ``activity_sets.service``."""

    @patch("modules.activities.activity_sets.crud.activity_sets_schema.ActivitySetsRead.model_validate")
    def test_success(self, mock_validate, mock_db):
        import modules.activities.activity_sets.crud as crud
        import modules.activities.activity_sets.models as m
        from modules.activities.activity_sets.schema import ActivitySetsRead

        mock_validate.return_value = ActivitySetsRead(
            id=uuid.uuid4(),
            activity_id=_ACTIVITY_ID,
            duration=300.0,
            set_type="interval",
            start_time=MagicMock(),
        )
        setup_mock_execute(
            mock_db, return_scalars_all=[mock_model(m.ActivitySets, id=uuid.uuid4(), activity_id=_ACTIVITY_ID)]
        )
        assert len(crud.get_activity_sets(activity_id=_ACTIVITY_ID, db=mock_db)) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity_sets.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert crud.get_activity_sets(activity_id=_ACTIVITY_ID, db=mock_db) == []


class TestGetActivitiesSets:
    """The batch read no longer joins the parent: it is handed scoped ids."""

    @patch("modules.activities.activity_sets.serializers.to_read_schema")
    def test_success(self, mock_to_read, mock_db):
        import modules.activities.activity_sets.crud as crud
        import modules.activities.activity_sets.models as m

        mock_to_read.return_value = MagicMock()
        mock_db.scalars.return_value.all.return_value = [
            MagicMock(spec=m.ActivitySets, id=uuid.uuid4(), activity_id=_ACTIVITY_ID)
        ]

        assert len(crud.get_activities_sets(activity_ids=[_ACTIVITY_ID], db=mock_db)) == 1

    def test_empty_ids_short_circuits(self, mock_db):
        import modules.activities.activity_sets.crud as crud

        assert crud.get_activities_sets(activity_ids=[], db=mock_db) == []
        mock_db.scalars.assert_not_called()

    def test_no_rows(self, mock_db):
        import modules.activities.activity_sets.crud as crud

        mock_db.scalars.return_value.all.return_value = []

        assert crud.get_activities_sets(activity_ids=[_ACTIVITY_ID], db=mock_db) == []


def _ids(*numbers):
    return [uuid.UUID(int=n) for n in numbers]


class TestOrdering:
    """Rows come back by their natural key; the id only breaks a tie."""

    def _row(self, row_id, key):
        import modules.activities.activity_sets.models as m

        return m.ActivitySets(id=row_id, activity_id=_ACTIVITY_ID, duration=1, set_type="active", start_time=key)

    def _read(self, rows, **page):
        from tests._helpers.db import create_sqlite_session

        import modules.activities.activity_sets.crud as crud

        db = create_sqlite_session()
        try:
            for row in rows:
                db.add(row)
            db.commit()
            return [(r.start_time, r.id) for r in crud.get_activity_sets(_ACTIVITY_ID, db, **page)]
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
