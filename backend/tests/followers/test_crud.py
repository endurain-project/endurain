from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


class TestGetAllFollowersByUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m

        f = MagicMock(spec=m.Follower, id=1, following_id=1)
        mock_db.scalars.return_value.all.return_value = [f]
        r = crud.get_all_followers_by_user_id(user_id=1, db=mock_db)
        assert r == [f]

    def test_empty(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_all_followers_by_user_id(user_id=1, db=mock_db)
        assert r == []

    def test_db_error(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_all_followers_by_user_id(user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetAcceptedFollowersByUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m

        f = MagicMock(spec=m.Follower, id=1, following_id=1, is_accepted=True)
        mock_db.scalars.return_value.all.return_value = [f]
        r = crud.get_accepted_followers_by_user_id(user_id=1, db=mock_db)
        assert r == [f]

    def test_empty(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_accepted_followers_by_user_id(user_id=1, db=mock_db)
        assert r == []

    def test_db_error(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_accepted_followers_by_user_id(user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetAllFollowingByUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m

        f = MagicMock(spec=m.Follower, id=1, follower_id=1)
        mock_db.scalars.return_value.all.return_value = [f]
        r = crud.get_all_following_by_user_id(user_id=1, db=mock_db)
        assert r == [f]

    def test_empty(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_all_following_by_user_id(user_id=1, db=mock_db)
        assert r == []

    def test_db_error(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_all_following_by_user_id(user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetAcceptedFollowingByUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m

        f = MagicMock(spec=m.Follower, id=1, follower_id=1, is_accepted=True)
        mock_db.scalars.return_value.all.return_value = [f]
        r = crud.get_accepted_following_by_user_id(user_id=1, db=mock_db)
        assert r == [f]

    def test_empty(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_accepted_following_by_user_id(user_id=1, db=mock_db)
        assert r == []

    def test_db_error(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_accepted_following_by_user_id(user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestCountFollowersByUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalar.return_value = 10
        r = crud.count_followers_by_user_id(user_id=1, db=mock_db)
        assert r == 10

    def test_success_accepted_only(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalar.return_value = 5
        r = crud.count_followers_by_user_id(user_id=1, db=mock_db, accepted_only=True)
        assert r == 5

    def test_none_returns_zero(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalar.return_value = None
        r = crud.count_followers_by_user_id(user_id=1, db=mock_db)
        assert r == 0

    def test_db_error(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalar.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.count_followers_by_user_id(user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestCountFollowingByUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalar.return_value = 8
        r = crud.count_following_by_user_id(user_id=1, db=mock_db)
        assert r == 8

    def test_success_accepted_only(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalar.return_value = 3
        r = crud.count_following_by_user_id(user_id=1, db=mock_db, accepted_only=True)
        assert r == 3

    def test_none_returns_zero(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalar.return_value = None
        r = crud.count_following_by_user_id(user_id=1, db=mock_db)
        assert r == 0

    def test_db_error(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalar.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.count_following_by_user_id(user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetFollowerForUserIdAndTargetUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m

        f = MagicMock(spec=m.Follower, id=1, follower_id=1, following_id=2)
        mock_db.scalars.return_value.first.return_value = f
        r = crud.get_follower_for_user_id_and_target_user_id(user_id=1, target_user_id=2, db=mock_db)
        assert r is f

    def test_not_found(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.first.return_value = None
        r = crud.get_follower_for_user_id_and_target_user_id(user_id=1, target_user_id=999, db=mock_db)
        assert r is None

    def test_db_error(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.get_follower_for_user_id_and_target_user_id(user_id=1, target_user_id=2, db=mock_db)
        assert e.value.status_code == 500


class TestCreateFollower:
    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    @patch("modules.followers.crud.notifications_utils.create_new_follower_request_notification")
    async def test_success(self, mock_notif, mock_get_follow, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m

        mock_get_follow.return_value = None
        new_follow = MagicMock(spec=m.Follower, id=1, follower_id=1, following_id=2)
        mock_db.refresh.side_effect = lambda x: None

        with patch.object(crud.followers_models, "Follower", return_value=new_follow):
            r = await crud.create_follower(user_id=1, target_user_id=2, websocket_manager=MagicMock(), db=mock_db)
        assert r is new_follow
        mock_db.add.assert_called_once_with(new_follow)
        mock_db.commit.assert_called_once()
        mock_notif.assert_awaited_once()

    async def test_self_follow(self, mock_db):
        import modules.followers.crud as crud

        with pytest.raises(HTTPException) as e:
            await crud.create_follower(user_id=1, target_user_id=1, websocket_manager=MagicMock(), db=mock_db)
        assert e.value.status_code == 400

    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    async def test_already_exists(self, mock_get_follow, mock_db):
        import modules.followers.crud as crud

        mock_get_follow.return_value = MagicMock()
        with pytest.raises(HTTPException) as e:
            await crud.create_follower(user_id=1, target_user_id=2, websocket_manager=MagicMock(), db=mock_db)
        assert e.value.status_code == 409

    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    @patch("modules.followers.crud.core_logger.print_to_log")
    async def test_integrity_error(self, mock_log, mock_get_follow, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m

        mock_get_follow.return_value = None
        mock_db.commit.side_effect = IntegrityError("stmt", "params", "orig")

        with (
            patch.object(crud.followers_models, "Follower", return_value=MagicMock(spec=m.Follower)),
            pytest.raises(HTTPException) as e,
        ):
            await crud.create_follower(user_id=1, target_user_id=2, websocket_manager=MagicMock(), db=mock_db)
        assert e.value.status_code == 409
        mock_db.rollback.assert_called_once()

    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    @patch("modules.followers.crud.core_logger.print_to_log")
    async def test_sqlalchemy_error(self, mock_log, mock_get_follow, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m

        mock_get_follow.return_value = None
        mock_db.commit.side_effect = SQLAlchemyError("db error")

        with (
            patch.object(crud.followers_models, "Follower", return_value=MagicMock(spec=m.Follower)),
            pytest.raises(HTTPException) as e,
        ):
            await crud.create_follower(user_id=1, target_user_id=2, websocket_manager=MagicMock(), db=mock_db)
        assert e.value.status_code == 500
        mock_db.rollback.assert_called_once()


class TestAcceptFollower:
    @patch("modules.followers.crud.notifications_utils.create_accepted_follower_request_notification")
    async def test_success(self, mock_notif, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m

        accept_follow = MagicMock(spec=m.Follower, id=1, follower_id=2, following_id=1, is_accepted=False)
        mock_db.scalars.return_value.first.return_value = accept_follow

        await crud.accept_follower(user_id=1, target_user_id=2, websocket_manager=MagicMock(), db=mock_db)
        assert accept_follow.is_accepted is True
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(accept_follow)
        mock_notif.assert_awaited_once()

    async def test_not_found(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.first.return_value = None
        with pytest.raises(HTTPException) as e:
            await crud.accept_follower(user_id=1, target_user_id=999, websocket_manager=MagicMock(), db=mock_db)
        assert e.value.status_code == 404

    @patch("modules.followers.crud.core_logger.print_to_log")
    async def test_sqlalchemy_error(self, mock_log, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m

        accept_follow = MagicMock(spec=m.Follower, id=1, is_accepted=False)
        mock_db.scalars.return_value.first.return_value = accept_follow
        mock_db.commit.side_effect = SQLAlchemyError("db error")

        with pytest.raises(HTTPException) as e:
            await crud.accept_follower(user_id=1, target_user_id=2, websocket_manager=MagicMock(), db=mock_db)
        assert e.value.status_code == 500
        mock_db.rollback.assert_called_once()


class TestDeleteFollower:
    def test_success(self, mock_db):
        import modules.followers.crud as crud

        r = MagicMock()
        r.rowcount = 1
        mock_db.execute.return_value = r
        crud.delete_follower(user_id=1, target_user_id=2, db=mock_db)
        mock_db.commit.assert_called_once()

    def test_not_found(self, mock_db):
        import modules.followers.crud as crud

        r = MagicMock()
        r.rowcount = 0
        mock_db.execute.return_value = r
        with pytest.raises(HTTPException) as e:
            crud.delete_follower(user_id=1, target_user_id=999, db=mock_db)
        assert e.value.status_code == 404
        mock_db.rollback.assert_called_once()

    def test_db_error(self, mock_db):
        import modules.followers.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(HTTPException) as e:
            crud.delete_follower(user_id=1, target_user_id=2, db=mock_db)
        assert e.value.status_code == 500
