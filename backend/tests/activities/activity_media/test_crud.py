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

        mock_media_model.return_value = MagicMock()
        crud.create_activity_media(activity_id=1, media_path="/path/to/file.jpg", db=mock_db)
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch("modules.activities.activity_media.crud.activity_media_models.ActivityMedia")
    def test_db_error(self, mock_media_model, mock_db):
        import modules.activities.activity_media.crud as crud

        mock_media_model.return_value = MagicMock()
        mock_db.commit.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.create_activity_media(activity_id=1, media_path="/path/to/file.jpg", db=mock_db)
        assert e.value.status_code == 500


class TestGetActivityMedia:
    @patch("modules.activities.activity_media.crud.activity_crud.get_activity_by_id_from_user_id")
    def test_success(self, mock_get_act, mock_db):
        import modules.activities.activity_media.crud as crud
        import modules.activities.activity_media.models as am

        mock_get_act.return_value = MagicMock()
        setup_mock_execute(mock_db, return_scalars_all=[mock_model(am.ActivityMedia, id=1, activity_id=1)])
        r = crud.get_activity_media(activity_id=1, token_user_id=1, db=mock_db)
        assert len(r) == 1

    @patch("modules.activities.activity_media.crud.activity_crud.get_activity_by_id_from_user_id")
    def test_empty(self, mock_get_act, mock_db):
        import modules.activities.activity_media.crud as crud

        mock_get_act.return_value = MagicMock()
        setup_mock_execute(mock_db, return_scalars_all=[])
        r = crud.get_activity_media(activity_id=1, token_user_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_media.crud.activity_crud.get_activity_by_id_from_user_id")
    def test_not_found(self, mock_get_act, mock_db):
        import modules.activities.activity_media.crud as crud

        mock_get_act.return_value = None
        r = crud.get_activity_media(activity_id=1, token_user_id=1, db=mock_db)
        assert r is None

    @patch("modules.activities.activity_media.crud.activity_crud.get_activity_by_id_from_user_id")
    def test_db_error(self, mock_get_act, mock_db):
        import modules.activities.activity_media.crud as crud

        mock_get_act.return_value = MagicMock()
        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_activity_media(activity_id=1, token_user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetAllActivityMedia:
    def test_success(self, mock_db):
        import modules.activities.activity_media.crud as crud
        import modules.activities.activity_media.models as m

        setup_mock_execute(mock_db, return_scalars_all=[MagicMock(spec=m.ActivityMedia, id=1)])
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
        import modules.activities.activity.models as am
        import modules.activities.activity_media.crud as crud
        import modules.activities.activity_media.models as mm

        mock_activity = MagicMock(spec=am.Activity, id=1, user_id=1)
        mock_media = MagicMock(spec=mm.ActivityMedia, id=1, activity_id=1)
        mock_db.scalars.return_value.all.side_effect = [
            [mock_activity],
            [mock_media],
        ]
        r = crud.get_activities_media(activity_ids=[1], token_user_id=1, db=mock_db)
        assert len(r) == 1

    def test_empty_ids(self, mock_db):
        import modules.activities.activity_media.crud as crud

        r = crud.get_activities_media(activity_ids=[], token_user_id=1, db=mock_db)
        assert r == []

    def test_no_activities(self, mock_db):
        import modules.activities.activity_media.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_activities_media(activity_ids=[1], token_user_id=1, db=mock_db)
        assert r == []

    def test_no_allowed_ids(self, mock_db):
        import modules.activities.activity.models as am
        import modules.activities.activity_media.crud as crud

        mock_activity = MagicMock(spec=am.Activity, id=1, user_id=2)
        mock_db.scalars.return_value.all.return_value = [mock_activity]
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
            crud.create_activity_media(activity_id=1, media_path="/path/to/file.jpg", db=mock_db)
        assert e.value.status_code == 409


class TestCreateActivityMedias:
    @patch("modules.activities.activity_media.crud.activity_media_models.ActivityMedia")
    def test_success(self, mock_media_model, mock_db):
        import modules.activities.activity_media.crud as crud
        from modules.activities.activity_media.schema import ActivityMedia

        mock_media_model.return_value = MagicMock()
        media_list = [ActivityMedia(activity_id=1, media_path="/p.jpg", media_type=1)]
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
        from modules.activities.activity_media.schema import ActivityMedia

        mock_media_model.return_value = MagicMock()
        mock_db.commit.side_effect = SQLAlchemyError("err")
        media_list = [ActivityMedia(activity_id=1, media_path="/p.jpg", media_type=1)]
        with pytest.raises(HTTPException) as e:
            crud.create_activity_medias(media_list, 1, mock_db)
        assert e.value.status_code == 500


class TestEditActivityMediaMediaPath:
    def test_success(self, mock_db):
        import modules.activities.activity_media.crud as crud
        import modules.activities.activity_media.models as m

        mock_media = MagicMock(spec=m.ActivityMedia, id=1, media_path="/old/path")
        mock_db.scalars.return_value.first.return_value = mock_media
        result = crud.edit_activity_media_media_path(1, "/new/path", mock_db)
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(mock_media)
        assert result == mock_media

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
    @patch("modules.activities.activity_media.crud.core_file_uploads.safe_remove_within")
    @patch("modules.activities.activity_media.crud.core_config.settings")
    @patch("modules.activities.activity_media.crud.activity_crud.get_activity_by_id_from_user_id")
    def test_success(self, mock_get_act, mock_settings, mock_remove, mock_db):
        import modules.activities.activity_media.crud as crud
        import modules.activities.activity_media.models as m

        mock_media = MagicMock(spec=m.ActivityMedia, id=1, activity_id=1, media_path="/path/file.jpg")
        mock_db.scalars.return_value.first.return_value = mock_media
        mock_get_act.return_value = MagicMock(user_id=1)
        crud.delete_activity_media(1, 1, mock_db)
        mock_db.delete.assert_called_once_with(mock_media)
        mock_db.commit.assert_called_once()
        mock_remove.assert_called_once()

    def test_not_found_media(self, mock_db):
        import modules.activities.activity_media.crud as crud

        mock_db.scalars.return_value.first.return_value = None
        with pytest.raises(HTTPException) as e:
            crud.delete_activity_media(1, 1, mock_db)
        assert e.value.status_code == 404

    @patch("modules.activities.activity_media.crud.activity_crud.get_activity_by_id_from_user_id")
    def test_not_found_activity(self, mock_get_act, mock_db):
        import modules.activities.activity_media.crud as crud
        import modules.activities.activity_media.models as m

        mock_db.scalars.return_value.first.return_value = MagicMock(spec=m.ActivityMedia, id=1, activity_id=1)
        mock_get_act.return_value = None
        with pytest.raises(HTTPException) as e:
            crud.delete_activity_media(1, 1, mock_db)
        assert e.value.status_code == 404

    @patch("modules.activities.activity_media.crud.activity_crud.get_activity_by_id_from_user_id")
    def test_forbidden(self, mock_get_act, mock_db):
        import modules.activities.activity_media.crud as crud
        import modules.activities.activity_media.models as m

        mock_db.scalars.return_value.first.return_value = MagicMock(spec=m.ActivityMedia, id=1, activity_id=1)
        mock_get_act.return_value = MagicMock(user_id=2)
        with pytest.raises(HTTPException) as e:
            crud.delete_activity_media(1, 1, mock_db)
        assert e.value.status_code == 403

    @patch("modules.activities.activity_media.crud.activity_crud.get_activity_by_id_from_user_id")
    def test_db_error(self, mock_get_act, mock_db):
        import modules.activities.activity_media.crud as crud
        import modules.activities.activity_media.models as m

        mock_db.scalars.return_value.first.return_value = MagicMock(spec=m.ActivityMedia, id=1, activity_id=1)
        mock_get_act.return_value = MagicMock(user_id=1)
        mock_db.commit.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.delete_activity_media(1, 1, mock_db)
        assert e.value.status_code == 500

    @patch("modules.activities.activity_media.crud.core_logger.print_to_log")
    @patch("modules.activities.activity_media.crud.core_file_uploads.safe_remove_within")
    @patch("modules.activities.activity_media.crud.core_config.settings")
    @patch("modules.activities.activity_media.crud.activity_crud.get_activity_by_id_from_user_id")
    def test_safe_remove_error(self, mock_get_act, mock_settings, mock_remove, mock_log, mock_db):
        import modules.activities.activity_media.crud as crud
        import modules.activities.activity_media.models as m

        mock_media = MagicMock(spec=m.ActivityMedia, id=1, activity_id=1, media_path="/path/file.jpg")
        mock_db.scalars.return_value.first.return_value = mock_media
        mock_get_act.return_value = MagicMock(user_id=1)
        mock_remove.side_effect = HTTPException(status_code=400, detail="Path outside media dir")
        crud.delete_activity_media(1, 1, mock_db)
        mock_db.delete.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_log.assert_called_once()
