from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from tests._helpers.db import create_sqlite_session, setup_mock_execute
from tests._helpers.models import mock_model


class TestGetUserActivities:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success(self, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        a = mock_model(am.Activity, id=1, user_id=1)
        setup_mock_execute(mock_db, return_scalars_all=[a])
        mock_ser.return_value = MagicMock()

        r = crud.get_user_activities(user_id=1, db=mock_db, user_is_owner=True)
        assert r is not None and len(r) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert crud.get_user_activities(user_id=1, db=mock_db) is None

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_user_activities(user_id=1, db=mock_db)
        assert e.value.status_code == 500

    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_with_filters(self, mock_ser, mock_db):
        from datetime import date

        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1, user_id=1)])
        mock_ser.return_value = MagicMock()
        r = crud.get_user_activities(
            user_id=1,
            db=mock_db,
            activity_type=1,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            name_search="Test",
        )
        assert r is not None


class TestGetUserActivitiesWithPagination:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success(self, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1)])
        mock_ser.return_value = MagicMock()
        r = crud.get_user_activities_with_pagination(user_id=1, db=mock_db, page_number=1, num_records=10)
        assert r is not None and len(r) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert crud.get_user_activities_with_pagination(user_id=1, db=mock_db) is None

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_user_activities_with_pagination(user_id=1, db=mock_db)
        assert e.value.status_code == 500

    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_sort_by_location(self, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1)])
        mock_ser.return_value = MagicMock()
        r = crud.get_user_activities_with_pagination(
            user_id=1,
            db=mock_db,
            page_number=1,
            num_records=10,
            sort_by="location",
            sort_order="asc",
        )
        assert r is not None

    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_sort_by_numeric(self, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1)])
        mock_ser.return_value = MagicMock()
        r = crud.get_user_activities_with_pagination(
            user_id=1,
            db=mock_db,
            page_number=1,
            num_records=10,
            sort_by="distance",
            sort_order="desc",
        )
        assert r is not None


class TestGetAllActivities:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success(self, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1)])
        mock_ser.return_value = MagicMock()
        r = crud.get_all_activities(db=mock_db)
        assert r is not None and len(r) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert crud.get_all_activities(db=mock_db) is None

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_all_activities(db=mock_db)
        assert e.value.status_code == 500


class TestGetActivitiesPerTimeframe:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success(self, mock_ser, mock_db):
        from datetime import UTC, datetime

        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1, user_id=1)])
        mock_ser.return_value = MagicMock()
        r = crud.get_user_activities_per_timeframe(
            user_id=1,
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 31, tzinfo=UTC),
            db=mock_db,
            user_is_owner=True,
        )
        assert r is not None and len(r) == 1

    def test_empty(self, mock_db):
        from datetime import UTC, datetime

        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        r = crud.get_user_activities_per_timeframe(
            user_id=1, start=datetime(2024, 1, 1, tzinfo=UTC), end=datetime(2024, 1, 31, tzinfo=UTC), db=mock_db
        )
        assert r is None

    def test_db_error(self, mock_db):
        from datetime import UTC, datetime

        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_user_activities_per_timeframe(
                user_id=1,
                start=datetime(2024, 1, 1, tzinfo=UTC),
                end=datetime(2024, 1, 31, tzinfo=UTC),
                db=mock_db,
            )
        assert e.value.status_code == 500


class TestGetActivityByID:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success(self, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        a = mock_model(am.Activity, id=1, user_id=1)
        setup_mock_execute(mock_db, return_one_or_none=a)
        mock_ser.return_value = MagicMock()
        r = crud.get_activity_by_id(activity_id=1, db=mock_db)
        assert r is not None

    def test_not_found(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_one_or_none=None)
        assert crud.get_activity_by_id(activity_id=999, db=mock_db) is None

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activity_by_id(activity_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestCreateActivity:
    @patch("modules.activities.activity.crud.get_activity_by_start_time")
    @patch("modules.activities.activity.crud._transform_schema_activity_to_model_activity")
    def test_success(self, mock_transform, mock_check, mock_db):
        import modules.activities.activity.crud as crud

        mock_check.return_value = None
        m = MagicMock()
        m.id = 1
        mock_transform.return_value = m
        a = MagicMock()
        a.user_id = 1
        a.start_time = datetime.now(UTC)
        r = crud.create_activity(activity=a, db=mock_db)
        assert r is not None
        mock_db.add.assert_called_once()

    def test_missing_start_time_raises_422(self, mock_db):
        import modules.activities.activity.crud as crud

        a = MagicMock()
        a.user_id = 1
        a.start_time = None
        with pytest.raises(HTTPException) as e:
            crud.create_activity(activity=a, db=mock_db)
        assert e.value.status_code == 422
        mock_db.add.assert_not_called()

    def test_missing_user_id_raises_422(self, mock_db):
        import modules.activities.activity.crud as crud

        a = MagicMock()
        a.user_id = None
        a.start_time = datetime.now(UTC)
        with pytest.raises(HTTPException) as e:
            crud.create_activity(activity=a, db=mock_db)
        assert e.value.status_code == 422
        mock_db.add.assert_not_called()

    @patch("modules.activities.activity.crud.get_activity_by_start_time")
    @patch("modules.activities.activity.crud._transform_schema_activity_to_model_activity")
    def test_duplicate_start_time(self, mock_transform, mock_check, mock_db):
        import modules.activities.activity.crud as crud

        mock_check.return_value = MagicMock()
        m = MagicMock()
        m.id = 1
        mock_transform.return_value = m
        a = MagicMock()
        a.user_id = 1
        a.start_time = datetime.now(UTC)
        a.is_hidden = False
        crud.create_activity(activity=a, db=mock_db)
        # A duplicate start time marks the activity hidden; the caller forwards
        # this (via publish_activity_created) to the notification subscriber,
        # which raises the duplicate variant. No notification is emitted inline.
        assert a.is_hidden is True

    @patch("modules.activities.activity.crud.get_activity_by_start_time")
    @patch("modules.activities.activity.crud._transform_schema_activity_to_model_activity")
    def test_persists_dedup_key(self, mock_transform, mock_check, mock_db):
        import modules.activities.activity.crud as crud

        mock_check.return_value = None
        m = MagicMock()
        m.id = 1
        mock_transform.return_value = m
        a = MagicMock()
        a.user_id = 1
        a.start_time = datetime.now(UTC)
        crud.create_activity(activity=a, db=mock_db, dedup_key="strava:99")
        # The idempotency key is stored on the ORM row so future re-imports of the
        # same source can be recognised as duplicates.
        assert m.dedup_key == "strava:99"

    @patch("modules.activities.activity.crud.get_activity_by_start_time")
    @patch("modules.activities.activity.crud._transform_schema_activity_to_model_activity")
    def test_db_error(self, mock_transform, mock_check, mock_db):
        import modules.activities.activity.crud as crud

        mock_check.return_value = None
        mock_transform.return_value = MagicMock()
        mock_db.add.side_effect = SQLAlchemyError("err")
        a = MagicMock()
        a.user_id = 1
        a.start_time = "2024-01-01T10:00:00+00:00"
        with pytest.raises(HTTPException) as e:
            crud.create_activity(activity=a, db=mock_db)
        assert e.value.status_code == 500
        mock_db.rollback.assert_called_once()


class TestEditActivity:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success(self, mock_ser, mock_db):
        from pydantic import BaseModel

        import modules.activities.activity.crud as crud

        db_act = MagicMock()
        db_act.id = 1
        setup_mock_execute(mock_db, return_one_or_none=db_act)
        mock_ser.return_value = MagicMock()

        class A(BaseModel):
            id: int = 1
            name: str = "U"

        r = crud.edit_activity(user_id=1, activity_attributes=A(), db=mock_db)
        assert r is not None

    def test_not_found(self, mock_db):
        from pydantic import BaseModel

        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_one_or_none=None)

        class A(BaseModel):
            id: int = 999
            name: str = "U"

        with pytest.raises(HTTPException) as e:
            crud.edit_activity(user_id=1, activity_attributes=A(), db=mock_db)
        assert e.value.status_code == 404

    def test_invalid_type(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_one_or_none=MagicMock())
        with pytest.raises(TypeError, match="Pydantic"):
            crud.edit_activity(user_id=1, activity_attributes=type("Nope", (), {"id": 1})(), db=mock_db)

    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    @patch("modules.activities.activity.crud.core_sanitization.sanitize_markdown")
    def test_sanitization(self, mock_sanitize, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.schema as s

        mock_sanitize.side_effect = lambda x: f"sanitized_{x}"
        mock_ser.return_value = MagicMock()
        db_act = MagicMock()
        db_act.id = 1
        setup_mock_execute(mock_db, return_one_or_none=db_act)

        attrs = s.ActivityEdit(id=1, name="test", activity_type=1, description="desc", private_notes="notes")
        crud.edit_activity(user_id=1, activity_attributes=attrs, db=mock_db)
        assert mock_sanitize.call_count == 2

    def test_db_error(self, mock_db):
        from pydantic import BaseModel

        import modules.activities.activity.crud as crud

        db_act = MagicMock()
        db_act.id = 1
        setup_mock_execute(mock_db, return_one_or_none=db_act)

        class A(BaseModel):
            id: int = 1
            name: str = "U"

        mock_db.commit.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.edit_activity(user_id=1, activity_attributes=A(), db=mock_db)
        assert e.value.status_code == 500
        mock_db.rollback.assert_called_once()


class TestDelete:
    def test_success(self, mock_db):
        import modules.activities.activity.crud as crud

        r = MagicMock()
        r.rowcount = 1
        mock_db.execute.return_value = r
        crud.delete_activity(activity_id=1, db=mock_db)
        mock_db.commit.assert_called_once()

    def test_not_found(self, mock_db):
        import modules.activities.activity.crud as crud

        r = MagicMock()
        r.rowcount = 0
        mock_db.execute.return_value = r
        with pytest.raises(HTTPException) as e:
            crud.delete_activity(activity_id=999, db=mock_db)
        assert e.value.status_code == 404

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.delete_activity(activity_id=1, db=mock_db)
        assert e.value.status_code == 500
        mock_db.rollback.assert_called_once()


class TestDistinctTypes:
    def test_success(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.return_value.scalars.return_value.all.return_value = [1, 2]
        r = crud.get_distinct_activity_types_for_user(user_id=1, db=mock_db)
        assert r == {1: "Run", 2: "Trail run"}

    def test_skips_none(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.return_value.scalars.return_value.all.return_value = [1, None]
        r = crud.get_distinct_activity_types_for_user(user_id=1, db=mock_db)
        assert None not in r

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_distinct_activity_types_for_user(user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGearActivities:
    def test_count(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.return_value.scalar.return_value = 5
        assert crud.get_gear_activities_count_by_user_id(user_id=1, gear_id=1, db=mock_db) == 5

    def test_count_none(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.return_value.scalar.return_value = None
        assert crud.get_gear_activities_count_by_user_id(user_id=1, gear_id=1, db=mock_db) == 0

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_gear_activities_count_by_user_id(user_id=1, gear_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestFollowing:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success(self, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1)])
        mock_ser.return_value = MagicMock()
        r = crud.get_user_following_activities(user_id=1, db=mock_db)
        assert r is not None and len(r) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert crud.get_user_following_activities(user_id=1, db=mock_db) is None

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_user_following_activities(user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestBulkSetGear:
    def test_success(self, mock_db):
        import modules.activities.activity.crud as crud

        r = MagicMock()
        r.rowcount = 2
        mock_db.execute.return_value = r
        assert crud.bulk_set_activities_gear_id(user_id=1, gear_assignments={1: 5}, db=mock_db) == 2

    def test_empty(self, mock_db):
        import modules.activities.activity.crud as crud

        assert crud.bulk_set_activities_gear_id(user_id=1, gear_assignments={}, db=mock_db) == 0

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.bulk_set_activities_gear_id(user_id=1, gear_assignments={1: 5}, db=mock_db)
        assert e.value.status_code == 500
        mock_db.rollback.assert_called_once()


class TestUpdateGear:
    def test_success(self, mock_db):
        import modules.activities.activity.crud as crud

        crud.update_activity_gear_id(activity_id=1, user_id=1, gear_id=5, db=mock_db)
        mock_db.commit.assert_called_once()

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.update_activity_gear_id(activity_id=1, user_id=1, gear_id=5, db=mock_db)
        assert e.value.status_code == 500
        mock_db.rollback.assert_called_once()


class TestActivityByStravaGarmin:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_by_strava_id(self, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_one_or_none=mock_model(am.Activity, id=1, strava_activity_id=123))
        mock_ser.return_value = MagicMock()
        r = crud.get_activity_by_strava_id_from_user_id(activity_strava_id=123, user_id=1, db=mock_db)
        assert r is not None

    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_by_garmin_id(self, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_one_or_none=mock_model(am.Activity, id=1, garminconnect_activity_id=456))
        mock_ser.return_value = MagicMock()
        r = crud.get_activity_by_garminconnect_id_from_user_id(activity_garminconnect_id=456, user_id=1, db=mock_db)
        assert r is not None

    def test_by_strava_id_not_found(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_one_or_none=None)
        assert crud.get_activity_by_strava_id_from_user_id(activity_strava_id=999, user_id=1, db=mock_db) is None

    def test_by_strava_id_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activity_by_strava_id_from_user_id(activity_strava_id=123, user_id=1, db=mock_db)
        assert e.value.status_code == 500

    def test_by_garmin_id_not_found(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_one_or_none=None)
        assert (
            crud.get_activity_by_garminconnect_id_from_user_id(activity_garminconnect_id=999, user_id=1, db=mock_db)
            is None
        )

    def test_by_garmin_id_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activity_by_garminconnect_id_from_user_id(activity_garminconnect_id=456, user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetAllActivitiesForMigration:
    def test_success(self, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1, user_id=2)])
        refs = crud.get_all_activities_for_migration(db=mock_db)
        assert len(refs) == 1
        assert refs[0].id == 1 and refs[0].user_id == 2

    def test_empty(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert crud.get_all_activities_for_migration(db=mock_db) == []

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_all_activities_for_migration(db=mock_db)
        assert e.value.status_code == 500


class TestGetUserActivitiesByGarminGear:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success(self, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1, user_id=1)])
        mock_ser.return_value = MagicMock()
        r = crud.get_user_activities_by_user_id_and_garminconnect_gear_set(user_id=1, db=mock_db)
        assert r is not None and len(r) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert crud.get_user_activities_by_user_id_and_garminconnect_gear_set(user_id=1, db=mock_db) is None

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_user_activities_by_user_id_and_garminconnect_gear_set(user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetUserActivitiesPerTimeframeAndType:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success(self, mock_ser, mock_db):
        from datetime import UTC, datetime

        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1, user_id=1)])
        mock_ser.return_value = MagicMock()
        r = crud.get_user_activities_per_timeframe_and_activity_type(
            user_id=1,
            activity_type=1,
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 31, tzinfo=UTC),
            db=mock_db,
            user_is_owner=True,
        )
        assert r is not None and len(r) == 1

    def test_empty(self, mock_db):
        from datetime import UTC, datetime

        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        r = crud.get_user_activities_per_timeframe_and_activity_type(
            user_id=1,
            activity_type=1,
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 31, tzinfo=UTC),
            db=mock_db,
        )
        assert r is None

    def test_db_error(self, mock_db):
        from datetime import UTC, datetime

        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_user_activities_per_timeframe_and_activity_type(
                user_id=1,
                activity_type=1,
                start=datetime(2024, 1, 1, tzinfo=UTC),
                end=datetime(2024, 1, 31, tzinfo=UTC),
                db=mock_db,
            )
        assert e.value.status_code == 500


class TestGetUserActivitiesPerTimeframeAndTypes:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success(self, mock_ser, mock_db):
        from datetime import UTC, datetime

        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1, user_id=1)])
        mock_ser.return_value = MagicMock()
        r = crud.get_user_activities_per_timeframe_and_activity_types(
            user_id=1,
            activity_types=[1, 2],
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 31, tzinfo=UTC),
            db=mock_db,
            user_is_owner=True,
        )
        assert r is not None and len(r) == 1

    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success_exclude_hidden(self, mock_ser, mock_db):
        from datetime import UTC, datetime

        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1, user_id=1)])
        mock_ser.return_value = MagicMock()
        r = crud.get_user_activities_per_timeframe_and_activity_types(
            user_id=1,
            activity_types=[1, 2],
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 31, tzinfo=UTC),
            db=mock_db,
            user_is_owner=True,
            exclude_hidden=True,
        )
        assert r is not None and len(r) == 1

    def test_empty(self, mock_db):
        from datetime import UTC, datetime

        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert (
            crud.get_user_activities_per_timeframe_and_activity_types(
                user_id=1,
                activity_types=[1],
                start=datetime(2024, 1, 1, tzinfo=UTC),
                end=datetime(2024, 1, 31, tzinfo=UTC),
                db=mock_db,
            )
            == []
        )

    def test_db_error(self, mock_db):
        from datetime import UTC, datetime

        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_user_activities_per_timeframe_and_activity_types(
                user_id=1,
                activity_types=[1],
                start=datetime(2024, 1, 1, tzinfo=UTC),
                end=datetime(2024, 1, 31, tzinfo=UTC),
                db=mock_db,
            )
        assert e.value.status_code == 500


class TestGetUserFollowingActivitiesPerTimeframe:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success(self, mock_ser, mock_db):
        from datetime import UTC, datetime

        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1)])
        mock_ser.return_value = MagicMock()
        r = crud.get_user_following_activities_per_timeframe(
            user_id=1,
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 31, tzinfo=UTC),
            db=mock_db,
        )
        assert r is not None and len(r) == 1

    def test_empty(self, mock_db):
        from datetime import UTC, datetime

        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert (
            crud.get_user_following_activities_per_timeframe(
                user_id=1,
                start=datetime(2024, 1, 1, tzinfo=UTC),
                end=datetime(2024, 1, 31, tzinfo=UTC),
                db=mock_db,
            )
            is None
        )

    def test_db_error(self, mock_db):
        from datetime import UTC, datetime

        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_user_following_activities_per_timeframe(
                user_id=1,
                start=datetime(2024, 1, 1, tzinfo=UTC),
                end=datetime(2024, 1, 31, tzinfo=UTC),
                db=mock_db,
            )
        assert e.value.status_code == 500


class TestGetUserFollowingActivitiesWithPagination:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success(self, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1)])
        mock_ser.return_value = MagicMock()
        r = crud.get_user_following_activities_with_pagination(user_id=1, page_number=1, num_records=10, db=mock_db)
        assert r is not None and len(r) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert (
            crud.get_user_following_activities_with_pagination(user_id=1, page_number=1, num_records=10, db=mock_db)
            is None
        )

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_user_following_activities_with_pagination(user_id=1, page_number=1, num_records=10, db=mock_db)
        assert e.value.status_code == 500


class TestGetUserActivitiesByGearId:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success(self, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1, user_id=1)])
        mock_ser.return_value = MagicMock()
        r = crud.get_user_activities_by_gear_id_and_user_id(user_id=1, gear_id=5, db=mock_db)
        assert r is not None and len(r) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert crud.get_user_activities_by_gear_id_and_user_id(user_id=1, gear_id=5, db=mock_db) is None

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_user_activities_by_gear_id_and_user_id(user_id=1, gear_id=5, db=mock_db)
        assert e.value.status_code == 500


class TestGetUserActivitiesByGearIdWithPagination:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success(self, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1, user_id=1)])
        mock_ser.return_value = MagicMock()
        r = crud.get_user_activities_by_gear_id_and_user_id_with_pagination(
            user_id=1, gear_id=5, page_number=1, num_records=10, db=mock_db
        )
        assert r is not None and len(r) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert (
            crud.get_user_activities_by_gear_id_and_user_id_with_pagination(
                user_id=1, gear_id=5, page_number=1, num_records=10, db=mock_db
            )
            is None
        )

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_user_activities_by_gear_id_and_user_id_with_pagination(
                user_id=1, gear_id=5, page_number=1, num_records=10, db=mock_db
            )
        assert e.value.status_code == 500


class TestGetActivityByIdFromUserIdOrHasVisibility:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    @patch("modules.activities.activity.crud.activities_serializers.apply_visibility_mask")
    def test_success_as_owner(self, mock_mask, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        a = mock_model(am.Activity, id=1, user_id=1)
        setup_mock_execute(mock_db, return_one_or_none=a)
        mock_ser.return_value = MagicMock()
        r = crud.get_activity_by_id_from_user_id_or_has_visibility(activity_id=1, user_id=1, db=mock_db)
        assert r is not None

    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    @patch("modules.activities.activity.crud.activities_serializers.apply_visibility_mask")
    def test_success_as_visible_non_owner(self, mock_mask, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        a = mock_model(am.Activity, id=1, user_id=2, visibility=0)
        setup_mock_execute(mock_db, return_one_or_none=a)
        mock_ser.return_value = MagicMock()
        r = crud.get_activity_by_id_from_user_id_or_has_visibility(activity_id=1, user_id=1, db=mock_db)
        assert r is not None

    def test_not_found(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_one_or_none=None)
        assert crud.get_activity_by_id_from_user_id_or_has_visibility(activity_id=999, user_id=1, db=mock_db) is None

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activity_by_id_from_user_id_or_has_visibility(activity_id=1, user_id=1, db=mock_db)
        assert e.value.status_code == 500


@pytest.fixture
def sqlite_session():
    """Real in-memory SQLite session for access-control behavior tests."""
    session = create_sqlite_session()
    try:
        yield session
    finally:
        session.close()
        # StaticPool keeps the single sqlite3 connection open for the life of
        # the engine; session.close() alone doesn't release it, which leaks an
        # unclosed sqlite3.Connection until GC eventually collects it (showing
        # up as a ResourceWarning on an unrelated, later test). Dispose the
        # engine explicitly to close the connection deterministically.
        session.bind.dispose()


def _public_activity(**overrides):
    """Build a fully-populated ``Activity`` row, overridable per test."""
    import modules.activities.activity.models as am

    fields = {
        "user_id": 1,
        "distance": 1000,
        "activity_type": 1,
        "start_time": datetime(2024, 1, 1, tzinfo=UTC),
        "end_time": datetime(2024, 1, 1, 1, tzinfo=UTC),
        "created_at": datetime(2024, 1, 1, tzinfo=UTC),
        "total_elapsed_time": Decimal("3600"),
        "total_timer_time": Decimal("3600"),
        "visibility": 0,
        "is_hidden": False,
        "hide_start_time": False,
        "hide_location": False,
        "hide_map": False,
        "hide_hr": False,
        "hide_power": False,
        "hide_cadence": False,
        "hide_elevation": False,
        "hide_speed": False,
        "hide_pace": False,
        "hide_laps": False,
        "hide_workout_sets_steps": False,
        "hide_gear": False,
    }
    fields.update(overrides)
    return am.Activity(**fields)


class TestGetActivityByIdIfIsPublic:
    """Public single-activity access.

    The ``visibility`` / ``is_hidden`` filtering is enforced by the SQL
    ``WHERE`` clause, which a mocked ``Session`` cannot evaluate. Those
    access-control guarantees are therefore exercised against a real in-memory
    SQLite database; the remaining branches stay on the fast mock-DB path.
    """

    # --- branch coverage (mock DB) ---

    @patch("modules.activities.activity.crud.server_settings_utils.get_server_settings_or_404")
    def test_disabled_setting(self, mock_settings, mock_db):
        import modules.activities.activity.crud as crud

        mock_settings.return_value.public_shareable_links = False
        assert crud.get_activity_by_id_if_is_public(activity_id=1, db=mock_db) is None

    @patch("modules.activities.activity.crud.server_settings_utils.get_server_settings_or_404")
    def test_db_error(self, mock_settings, mock_db):
        import modules.activities.activity.crud as crud

        mock_settings.return_value.public_shareable_links = True
        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activity_by_id_if_is_public(activity_id=1, db=mock_db)
        assert e.value.status_code == 500

    # --- access-control behavior (real SQLite DB) ---

    @patch("modules.activities.activity.crud.server_settings_utils.get_server_settings_or_404")
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    @patch("modules.activities.activity.crud.activities_serializers.apply_visibility_mask")
    def test_serves_public_activity(self, mock_mask, mock_ser, mock_settings, sqlite_session):
        """Regression guard: a public, non-hidden activity is still served after the is_hidden filter."""
        import modules.activities.activity.crud as crud

        mock_settings.return_value.public_shareable_links = True
        mock_ser.return_value = MagicMock()
        sqlite_session.add(_public_activity(id=1, visibility=0, is_hidden=False))
        sqlite_session.commit()

        result = crud.get_activity_by_id_if_is_public(activity_id=1, db=sqlite_session)

        assert result is not None
        mock_ser.assert_called_once()
        assert mock_ser.call_args.args[0].id == 1

    @patch("modules.activities.activity.crud.server_settings_utils.get_server_settings_or_404")
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    @patch("modules.activities.activity.crud.activities_serializers.apply_visibility_mask")
    def test_excludes_hidden_activities(self, mock_mask, mock_ser, mock_settings, sqlite_session):
        """A hidden activity must never be served publicly, even when its visibility is public."""
        import modules.activities.activity.crud as crud

        mock_settings.return_value.public_shareable_links = True
        sqlite_session.add(_public_activity(id=1, visibility=0, is_hidden=True))
        sqlite_session.commit()

        result = crud.get_activity_by_id_if_is_public(activity_id=1, db=sqlite_session)

        assert result is None
        mock_ser.assert_not_called()

    @patch("modules.activities.activity.crud.server_settings_utils.get_server_settings_or_404")
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    @patch("modules.activities.activity.crud.activities_serializers.apply_visibility_mask")
    def test_excludes_non_public_visibility(self, mock_mask, mock_ser, mock_settings, sqlite_session):
        """Only ``visibility == 0`` (public) activities are served."""
        import modules.activities.activity.crud as crud

        mock_settings.return_value.public_shareable_links = True
        sqlite_session.add(_public_activity(id=1, visibility=1, is_hidden=False))
        sqlite_session.commit()

        result = crud.get_activity_by_id_if_is_public(activity_id=1, db=sqlite_session)

        assert result is None
        mock_ser.assert_not_called()

    @patch("modules.activities.activity.crud.server_settings_utils.get_server_settings_or_404")
    def test_not_found(self, mock_settings, sqlite_session):
        """A non-existent activity id returns None."""
        import modules.activities.activity.crud as crud

        mock_settings.return_value.public_shareable_links = True
        assert crud.get_activity_by_id_if_is_public(activity_id=999, db=sqlite_session) is None


class TestGetViewableActivityByIdForUser:
    """Child-resource authorization gate (OWASP A01 / IDOR).

    ``get_viewable_activity_by_id_for_user`` is the visibility check the child
    sub-resource reads (streams / laps / sets / workout-steps) apply before
    returning a parent activity's data, so a non-owner cannot read a private or
    followers-only activity's streams/laps/sets/steps by id. The public /
    followers / private / hidden filtering lives in the SQL ``WHERE`` clause, so
    the access-control guarantees are exercised against a real in-memory SQLite
    database; only the error branch stays on the mock-DB path.
    """

    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_owner_sees_own_private_activity(self, mock_ser, sqlite_session):
        import modules.activities.activity.crud as crud

        mock_ser.return_value = MagicMock()
        sqlite_session.add(_public_activity(id=1, user_id=2, visibility=2, is_hidden=False))
        sqlite_session.commit()

        result = crud.get_viewable_activity_by_id_for_user(activity_id=1, user_id=2, db=sqlite_session)

        assert result is not None
        # Returned unmasked (no apply_visibility_mask) so callers can read hide_* flags.
        assert mock_ser.call_args.args[0].id == 1

    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_non_owner_denied_private_activity(self, mock_ser, sqlite_session):
        """A non-owner must NOT read a private (visibility=2) activity by id."""
        import modules.activities.activity.crud as crud

        sqlite_session.add(_public_activity(id=1, user_id=2, visibility=2, is_hidden=False))
        sqlite_session.commit()

        result = crud.get_viewable_activity_by_id_for_user(activity_id=1, user_id=1, db=sqlite_session)

        assert result is None
        mock_ser.assert_not_called()

    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_non_owner_sees_public_activity(self, mock_ser, sqlite_session):
        import modules.activities.activity.crud as crud

        mock_ser.return_value = MagicMock()
        sqlite_session.add(_public_activity(id=1, user_id=2, visibility=0, is_hidden=False))
        sqlite_session.commit()

        result = crud.get_viewable_activity_by_id_for_user(activity_id=1, user_id=1, db=sqlite_session)

        assert result is not None

    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_non_owner_denied_hidden_public_activity(self, mock_ser, sqlite_session):
        """A hidden activity is never visible to a non-owner, even when public."""
        import modules.activities.activity.crud as crud

        sqlite_session.add(_public_activity(id=1, user_id=2, visibility=0, is_hidden=True))
        sqlite_session.commit()

        result = crud.get_viewable_activity_by_id_for_user(activity_id=1, user_id=1, db=sqlite_session)

        assert result is None
        mock_ser.assert_not_called()

    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_non_owner_denied_followers_only_without_follow(self, mock_ser, sqlite_session):
        """A followers-only (visibility=1) activity is denied without an accepted follow."""
        import modules.activities.activity.crud as crud

        sqlite_session.add(_public_activity(id=1, user_id=2, visibility=1, is_hidden=False))
        sqlite_session.commit()

        result = crud.get_viewable_activity_by_id_for_user(activity_id=1, user_id=1, db=sqlite_session)

        assert result is None
        mock_ser.assert_not_called()

    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_non_owner_denied_followers_only_with_pending_follow(self, mock_ser, sqlite_session):
        """A pending (unaccepted) follow does not grant followers-only access."""
        import modules.activities.activity.crud as crud
        import modules.followers.models as followers_models

        sqlite_session.add(_public_activity(id=1, user_id=2, visibility=1, is_hidden=False))
        sqlite_session.add(followers_models.Follower(follower_id=1, following_id=2, is_accepted=False))
        sqlite_session.commit()

        result = crud.get_viewable_activity_by_id_for_user(activity_id=1, user_id=1, db=sqlite_session)

        assert result is None
        mock_ser.assert_not_called()

    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_non_owner_sees_followers_only_with_accepted_follow(self, mock_ser, sqlite_session):
        """An accepted follower may read a followers-only activity."""
        import modules.activities.activity.crud as crud
        import modules.followers.models as followers_models

        mock_ser.return_value = MagicMock()
        sqlite_session.add(_public_activity(id=1, user_id=2, visibility=1, is_hidden=False))
        sqlite_session.add(followers_models.Follower(follower_id=1, following_id=2, is_accepted=True))
        sqlite_session.commit()

        result = crud.get_viewable_activity_by_id_for_user(activity_id=1, user_id=1, db=sqlite_session)

        assert result is not None
        assert mock_ser.call_args.args[0].id == 1

    def test_not_found(self, sqlite_session):
        import modules.activities.activity.crud as crud

        assert crud.get_viewable_activity_by_id_for_user(activity_id=999, user_id=1, db=sqlite_session) is None

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_viewable_activity_by_id_for_user(activity_id=1, user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetActivityByStartTime:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success_with_str(self, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        a = mock_model(am.Activity, id=1, user_id=1)
        setup_mock_execute(mock_db, return_one_or_none=a)
        mock_ser.return_value = MagicMock()
        r = crud.get_activity_by_start_time(start_time="2024-01-01T10:00:00+00:00", user_id=1, db=mock_db)
        assert r is not None

    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success_with_datetime_naive(self, mock_ser, mock_db):
        from datetime import datetime

        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        a = mock_model(am.Activity, id=1, user_id=1)
        setup_mock_execute(mock_db, return_one_or_none=a)
        mock_ser.return_value = MagicMock()
        r = crud.get_activity_by_start_time(start_time=datetime(2024, 1, 1, 10, 0), user_id=1, db=mock_db)
        assert r is not None

    def test_not_found(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_one_or_none=None)
        assert crud.get_activity_by_start_time(start_time="2024-01-01T10:00:00+00:00", user_id=1, db=mock_db) is None

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activity_by_start_time(start_time="2024-01-01T10:00:00+00:00", user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetActivityByDedupKey:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success(self, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        a = mock_model(am.Activity, id=1, user_id=1, dedup_key="strava:123")
        setup_mock_execute(mock_db, return_one_or_none=a)
        mock_ser.return_value = MagicMock()
        r = crud.get_activity_by_dedup_key(dedup_key="strava:123", user_id=1, db=mock_db)
        assert r is not None

    def test_not_found(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_one_or_none=None)
        assert crud.get_activity_by_dedup_key(dedup_key="strava:999", user_id=1, db=mock_db) is None

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activity_by_dedup_key(dedup_key="strava:123", user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetActivityByIdFromUserId:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success(self, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        a = mock_model(am.Activity, id=1, user_id=1)
        setup_mock_execute(mock_db, return_one_or_none=a)
        mock_ser.return_value = MagicMock()
        r = crud.get_activity_by_id_from_user_id(activity_id=1, user_id=1, db=mock_db)
        assert r is not None

    def test_not_found(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_one_or_none=None)
        assert crud.get_activity_by_id_from_user_id(activity_id=999, user_id=1, db=mock_db) is None

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activity_by_id_from_user_id(activity_id=1, user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetActivitiesIfContainsName:
    @patch("modules.activities.activity.crud.activities_serializers.serialize_activity")
    def test_success(self, mock_ser, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1, user_id=1)])
        mock_ser.return_value = MagicMock()
        r = crud.get_activities_if_contains_name(name="Test", user_id=1, db=mock_db)
        assert r is not None and len(r) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert crud.get_activities_if_contains_name(name="Test", user_id=1, db=mock_db) is None

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activities_if_contains_name(name="Test", user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestSetActivityThumbnailPath:
    def test_success(self, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        a = mock_model(am.Activity, id=1)
        setup_mock_execute(mock_db, return_one_or_none=a)
        crud.set_activity_thumbnail_path(activity_id=1, thumbnail_path="/path/to/thumb.png", db=mock_db)
        assert a.map_thumbnail_path == "/path/to/thumb.png"
        mock_db.commit.assert_called_once()

    def test_not_found(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_one_or_none=None)
        crud.set_activity_thumbnail_path(activity_id=999, thumbnail_path="/path/to/thumb.png", db=mock_db)
        mock_db.commit.assert_not_called()

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.set_activity_thumbnail_path(activity_id=1, thumbnail_path="/path/to/thumb.png", db=mock_db)
        assert e.value.status_code == 500
        mock_db.rollback.assert_called_once()


class TestClearAllActivityThumbnailPaths:
    def test_success(self, mock_db):
        import modules.activities.activity.crud as crud

        crud.clear_all_activity_thumbnail_paths(db=mock_db)
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        crud.clear_all_activity_thumbnail_paths(db=mock_db)
        mock_db.rollback.assert_called_once()


class TestGetActivitiesWithThumbnail:
    def test_success(self, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1)])
        r = crud.get_activities_with_thumbnail(db=mock_db)
        assert len(r) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert crud.get_activities_with_thumbnail(db=mock_db) == []

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        assert crud.get_activities_with_thumbnail(db=mock_db) == []


class TestGetActivitiesWithoutThumbnail:
    def test_success(self, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.Activity, id=1)])
        r = crud.get_activities_without_thumbnail(db=mock_db)
        assert len(r) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert crud.get_activities_without_thumbnail(db=mock_db) == []

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        assert crud.get_activities_without_thumbnail(db=mock_db) == []


class TestUpdateActivityLocation:
    def test_success(self, mock_db):
        import modules.activities.activity.crud as crud
        import modules.activities.activity.models as am

        a = mock_model(am.Activity, id=1)
        setup_mock_execute(mock_db, return_one_or_none=a)
        result = crud.update_activity_location(1, "Lisbon", "Belem", "Portugal", db=mock_db)
        assert result is True
        assert (a.city, a.town, a.country) == ("Lisbon", "Belem", "Portugal")
        mock_db.commit.assert_called_once()

    def test_not_found(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_one_or_none=None)
        result = crud.update_activity_location(999, "Lisbon", None, "Portugal", db=mock_db)
        assert result is False
        mock_db.commit.assert_not_called()

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.update_activity_location(1, "Lisbon", None, "Portugal", db=mock_db)
        assert e.value.status_code == 500
        mock_db.rollback.assert_called_once()


class TestGetActivitiesMissingLocation:
    def test_success(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[1, 2])
        r = crud.get_activities_missing_location(db=mock_db)
        assert [ref.id for ref in r] == [1, 2]

    def test_empty(self, mock_db):
        import modules.activities.activity.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert crud.get_activities_missing_location(db=mock_db) == []

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        assert crud.get_activities_missing_location(db=mock_db) == []


class TestEditUserActivitiesVisibility:
    def test_success(self, mock_db):
        import modules.activities.activity.crud as crud

        r = MagicMock()
        r.rowcount = 3
        mock_db.execute.return_value = r
        result = crud.edit_user_activities_visibility(user_id=1, visibility=0, db=mock_db)
        assert result == 3
        mock_db.commit.assert_called_once()

    def test_no_rows(self, mock_db):
        import modules.activities.activity.crud as crud

        r = MagicMock()
        r.rowcount = 0
        mock_db.execute.return_value = r
        result = crud.edit_user_activities_visibility(user_id=1, visibility=0, db=mock_db)
        assert result == 0

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.edit_user_activities_visibility(user_id=1, visibility=0, db=mock_db)
        assert e.value.status_code == 500
        mock_db.rollback.assert_called_once()


class TestDeleteAllStravaActivitiesForUser:
    def test_success(self, mock_db):
        import modules.activities.activity.crud as crud

        r = MagicMock()
        r.rowcount = 2
        mock_db.execute.return_value = r
        result = crud.delete_all_strava_activities_for_user(user_id=1, db=mock_db)
        assert result == 2
        mock_db.commit.assert_called_once()

    def test_no_deletions(self, mock_db):
        import modules.activities.activity.crud as crud

        r = MagicMock()
        r.rowcount = 0
        mock_db.execute.return_value = r
        result = crud.delete_all_strava_activities_for_user(user_id=1, db=mock_db)
        assert result == 0
        mock_db.commit.assert_not_called()

    def test_db_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.delete_all_strava_activities_for_user(user_id=1, db=mock_db)
        assert e.value.status_code == 500
        mock_db.rollback.assert_called_once()


class TestGetActivitiesWithLegacyThumbnailPath:
    def test_returns_refs(self, mock_db):
        import modules.activities.activity.crud as crud

        row = MagicMock(id=7, map_thumbnail_path="/data/x/7.png")
        setup_mock_execute(mock_db, return_scalars_all=[row])
        result = crud.get_activities_with_legacy_thumbnail_path(mock_db)
        assert len(result) == 1
        assert result[0].id == 7
        assert result[0].map_thumbnail_path == "/data/x/7.png"

    def test_returns_empty_on_error(self, mock_db):
        import modules.activities.activity.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("boom")
        assert crud.get_activities_with_legacy_thumbnail_path(mock_db) == []
