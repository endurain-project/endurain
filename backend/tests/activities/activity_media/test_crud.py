from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from tests._helpers.db import setup_mock_execute
from tests._helpers.models import mock_model


class TestCreateActivityMedia:
    @patch("modules.activities.activity_media.crud.activity_media_models.ActivityMedia")
    def test_success(self, mock_media_model, mock_db):
        import modules.activities.activity_media.crud as crud

        row = MagicMock(spec=["id", "activity_id", "media_path", "media_type"])
        row.id, row.activity_id, row.media_path, row.media_type = 1, 1, "1_abc123.jpg", 1
        mock_media_model.return_value = row

        result = crud.create_activity_media(activity_id=1, media_key="1_abc123.jpg", db=mock_db)
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        assert result.id == 1
        # CRUD hands back the storage key; resolving it to a URL is the service's job.
        assert result.media_path == "1_abc123.jpg"
        assert not hasattr(result, "url")

    @patch("modules.activities.activity_media.crud.activity_media_models.ActivityMedia")
    def test_db_error(self, mock_media_model, mock_db):
        import modules.activities.activity_media.crud as crud

        mock_media_model.return_value = MagicMock()
        mock_db.commit.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.create_activity_media(activity_id=1, media_key="1_abc123.jpg", db=mock_db)
        assert e.value.status_code == 500


class TestGetMediaForActivity:
    def test_success(self, mock_db):
        import modules.activities.activity_media.crud as crud
        import modules.activities.activity_media.models as am

        setup_mock_execute(
            mock_db,
            return_scalars_all=[mock_model(am.ActivityMedia, id=1, activity_id=1, media_path="x.jpg", media_type=1)],
        )
        r = crud.get_media_for_activity(activity_id=1, db=mock_db)
        assert len(r) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity_media.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        assert crud.get_media_for_activity(activity_id=1, db=mock_db) == []

    def test_db_error(self, mock_db):
        import modules.activities.activity_media.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_media_for_activity(activity_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetActivityMediaById:
    def test_success(self, mock_db):
        import modules.activities.activity_media.crud as crud
        import modules.activities.activity_media.models as am

        mock_db.scalars.return_value.first.return_value = mock_model(
            am.ActivityMedia, id=7, activity_id=1, media_path="x.jpg", media_type=1
        )
        result = crud.get_activity_media_by_id(7, mock_db)
        assert result is not None
        assert result.id == 7

    def test_missing_returns_none(self, mock_db):
        import modules.activities.activity_media.crud as crud

        mock_db.scalars.return_value.first.return_value = None
        assert crud.get_activity_media_by_id(7, mock_db) is None


class TestGetAllActivityMedia:
    def test_success(self, mock_db):
        import modules.activities.activity_media.crud as crud
        import modules.activities.activity_media.models as m

        setup_mock_execute(
            mock_db,
            return_scalars_all=[MagicMock(spec=m.ActivityMedia, id=1, activity_id=1, media_path="x.jpg", media_type=1)],
        )
        r = crud.get_all_activity_media(mock_db)
        assert len(r) == 1

    def test_empty(self, mock_db):
        import modules.activities.activity_media.crud as crud

        setup_mock_execute(mock_db, return_scalars_all=[])
        r = crud.get_all_activity_media(mock_db)
        assert r == []

    def test_db_error(self, mock_db):
        import modules.activities.activity_media.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_all_activity_media(mock_db)
        assert e.value.status_code == 500


class TestGetActivitiesMedia:
    def test_success(self, mock_db):
        import modules.activities.activity_media.crud as crud
        import modules.activities.activity_media.models as mm

        mock_media = MagicMock(spec=mm.ActivityMedia, id=1, activity_id=1, media_path="x.jpg", media_type=1)
        # First scalars() call returns the owned activity ids, second the media.
        mock_db.scalars.return_value.all.side_effect = [[1], [mock_media]]
        r = crud.get_activities_media(activity_ids=[1], token_user_id=1, db=mock_db)
        assert len(r) == 1

    def test_empty_ids(self, mock_db):
        import modules.activities.activity_media.crud as crud

        r = crud.get_activities_media(activity_ids=[], token_user_id=1, db=mock_db)
        assert r == []

    def test_no_allowed_ids(self, mock_db):
        import modules.activities.activity_media.crud as crud

        # The ownership filter is now in SQL, so an unowned id yields no rows.
        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_activities_media(activity_ids=[1], token_user_id=1, db=mock_db)
        assert r == []

    def test_db_error(self, mock_db):
        import modules.activities.activity_media.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activities_media(activity_ids=[1], token_user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestCreateActivityMediaIntegrity:
    @patch("modules.activities.activity_media.crud.activity_media_models.ActivityMedia")
    def test_integrity_error(self, mock_media_model, mock_db):
        import modules.activities.activity_media.crud as crud

        mock_media_model.return_value = MagicMock()
        mock_db.commit.side_effect = IntegrityError("stmt", "params", "orig")
        with pytest.raises(HTTPException) as e:
            crud.create_activity_media(activity_id=1, media_key="1_abc123.jpg", db=mock_db)
        assert e.value.status_code == 409


class TestCreateActivityMedias:
    @patch("modules.activities.activity_media.crud.activity_media_models.ActivityMedia")
    def test_success(self, mock_media_model, mock_db):
        import modules.activities.activity_media.crud as crud
        from modules.activities.activity_media.contracts import ActivityMediaCreate

        mock_media_model.return_value = MagicMock()
        media_list = [ActivityMediaCreate(media_path="1_p.jpg", media_type=1)]
        crud.create_activity_medias(media_list, 1, mock_db)
        mock_db.add_all.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_empty(self, mock_db):
        import modules.activities.activity_media.crud as crud

        crud.create_activity_medias([], 1, mock_db)
        mock_db.commit.assert_not_called()

    @patch("modules.activities.activity_media.crud.activity_media_models.ActivityMedia")
    def test_db_error(self, mock_media_model, mock_db):
        import modules.activities.activity_media.crud as crud
        from modules.activities.activity_media.contracts import ActivityMediaCreate

        mock_media_model.return_value = MagicMock()
        mock_db.commit.side_effect = SQLAlchemyError("err")
        media_list = [ActivityMediaCreate(media_path="1_p.jpg", media_type=1)]
        with pytest.raises(HTTPException) as e:
            crud.create_activity_medias(media_list, 1, mock_db)
        assert e.value.status_code == 500


class TestEditActivityMediaMediaPath:
    def test_success(self, mock_db):
        import modules.activities.activity_media.crud as crud
        import modules.activities.activity_media.models as m

        mock_media = MagicMock(spec=m.ActivityMedia, id=1, activity_id=1, media_path="/old/path", media_type=1)
        mock_db.scalars.return_value.first.return_value = mock_media
        result = crud.edit_activity_media_media_path(1, "/new/path", mock_db)
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_media)
        assert result.media_path == "/new/path"

    def test_not_found(self, mock_db):
        import modules.activities.activity_media.crud as crud

        mock_db.scalars.return_value.first.return_value = None
        with pytest.raises(HTTPException) as e:
            crud.edit_activity_media_media_path(1, "/new/path", mock_db)
        assert e.value.status_code == 404

    def test_db_error(self, mock_db):
        import modules.activities.activity_media.crud as crud
        import modules.activities.activity_media.models as m

        mock_db.scalars.return_value.first.return_value = MagicMock(spec=m.ActivityMedia)
        mock_db.commit.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.edit_activity_media_media_path(1, "/new/path", mock_db)
        assert e.value.status_code == 500


class TestDeleteActivityMedia:
    def test_success(self, mock_db):
        import modules.activities.activity_media.crud as crud
        import modules.activities.activity_media.models as m

        mock_media = MagicMock(spec=m.ActivityMedia, id=1, activity_id=1, media_path="/path/file.jpg")
        mock_db.scalars.return_value.first.return_value = mock_media
        crud.delete_activity_media(1, mock_db)
        mock_db.delete.assert_called_once_with(mock_media)
        mock_db.commit.assert_called_once()

    def test_not_found_media(self, mock_db):
        import modules.activities.activity_media.crud as crud

        mock_db.scalars.return_value.first.return_value = None
        with pytest.raises(HTTPException) as e:
            crud.delete_activity_media(1, mock_db)
        assert e.value.status_code == 404

    def test_db_error(self, mock_db):
        import modules.activities.activity_media.crud as crud
        import modules.activities.activity_media.models as m

        mock_db.scalars.return_value.first.return_value = MagicMock(spec=m.ActivityMedia, id=1, activity_id=1)
        mock_db.commit.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.delete_activity_media(1, mock_db)
        assert e.value.status_code == 500
