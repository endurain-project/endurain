from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import core.exceptions as core_exceptions


class TestGetAllFollowersByUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m
        from modules.followers.schema import FollowRelationship

        f = MagicMock(spec=m.Follower, follower_id=2, followee_id=1, status="accepted")
        mock_db.scalars.return_value.all.return_value = [f]
        r = crud.get_all_followers_by_user_id(user_id=1, db=mock_db)
        assert r == [FollowRelationship(follower_id=2, followee_id=1, status="accepted")]

    def test_empty(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_all_followers_by_user_id(user_id=1, db=mock_db)
        assert r == []

    def test_db_error(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_all_followers_by_user_id(user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetAcceptedFollowersByUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m
        from modules.followers.schema import FollowRelationship

        f = MagicMock(spec=m.Follower, follower_id=2, followee_id=1, status="accepted")
        mock_db.scalars.return_value.all.return_value = [f]
        r = crud.get_accepted_followers_by_user_id(user_id=1, db=mock_db)
        assert r == [FollowRelationship(follower_id=2, followee_id=1, status="accepted")]

    def test_empty(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_accepted_followers_by_user_id(user_id=1, db=mock_db)
        assert r == []

    def test_db_error(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_accepted_followers_by_user_id(user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetAllFollowingByUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m
        from modules.followers.schema import FollowRelationship

        f = MagicMock(spec=m.Follower, follower_id=1, followee_id=2, status="accepted")
        mock_db.scalars.return_value.all.return_value = [f]
        r = crud.get_all_following_by_user_id(user_id=1, db=mock_db)
        assert r == [FollowRelationship(follower_id=1, followee_id=2, status="accepted")]

    def test_empty(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_all_following_by_user_id(user_id=1, db=mock_db)
        assert r == []

    def test_db_error(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_all_following_by_user_id(user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetAcceptedFollowingByUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m
        from modules.followers.schema import FollowRelationship

        f = MagicMock(spec=m.Follower, follower_id=1, followee_id=2, status="accepted")
        mock_db.scalars.return_value.all.return_value = [f]
        r = crud.get_accepted_following_by_user_id(user_id=1, db=mock_db)
        assert r == [FollowRelationship(follower_id=1, followee_id=2, status="accepted")]

    def test_empty(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_accepted_following_by_user_id(user_id=1, db=mock_db)
        assert r == []

    def test_db_error(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
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
        with pytest.raises(core_exceptions.ProcessingError) as e:
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
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.count_following_by_user_id(user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestGetFollowerForUserIdAndTargetUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m
        from modules.followers.schema import FollowRelationship

        f = MagicMock(spec=m.Follower, follower_id=1, followee_id=2, status="pending")
        mock_db.scalars.return_value.first.return_value = f
        r = crud.get_follower_for_user_id_and_target_user_id(user_id=1, target_user_id=2, db=mock_db)
        assert r == FollowRelationship(follower_id=1, followee_id=2, status="pending")

    def test_not_found(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.first.return_value = None
        r = crud.get_follower_for_user_id_and_target_user_id(user_id=1, target_user_id=999, db=mock_db)
        assert r is None

    def test_db_error(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.get_follower_for_user_id_and_target_user_id(user_id=1, target_user_id=2, db=mock_db)
        assert e.value.status_code == 500


class TestListAcceptedFolloweeIds:
    def test_success(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.all.return_value = [2, 3]
        r = crud.list_accepted_followee_ids(user_id=1, db=mock_db)
        assert r == [2, 3]

    def test_empty(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        assert crud.list_accepted_followee_ids(user_id=1, db=mock_db) == []

    def test_db_error(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.list_accepted_followee_ids(user_id=1, db=mock_db)
        assert e.value.status_code == 500


class TestCreateFollower:
    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_success(self, mock_get_follow, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m
        from modules.followers.schema import FollowRelationship

        mock_get_follow.return_value = None
        new_follow = MagicMock(spec=m.Follower, follower_id=1, followee_id=2, status="pending")
        mock_db.refresh.side_effect = lambda x: None

        with patch.object(crud.followers_models, "Follower", return_value=new_follow):
            r = crud.create_follower(user_id=1, target_user_id=2, db=mock_db)
        assert r == FollowRelationship(follower_id=1, followee_id=2, status="pending")
        mock_db.add.assert_called_once_with(new_follow)
        mock_db.commit.assert_called_once()

    def test_self_follow(self, mock_db):
        import modules.followers.crud as crud

        with pytest.raises(core_exceptions.InvalidInputError) as e:
            crud.create_follower(user_id=1, target_user_id=1, db=mock_db)
        assert e.value.status_code == 400

    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_already_exists(self, mock_get_follow, mock_db):
        import modules.followers.crud as crud

        mock_get_follow.return_value = MagicMock()
        with pytest.raises(core_exceptions.ConflictError) as e:
            crud.create_follower(user_id=1, target_user_id=2, db=mock_db)
        assert e.value.status_code == 409

    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_integrity_error(self, mock_get_follow, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m

        mock_get_follow.return_value = None
        mock_db.commit.side_effect = IntegrityError("stmt", "params", "orig")

        with (
            patch.object(crud.followers_models, "Follower", return_value=MagicMock(spec=m.Follower)),
            pytest.raises(core_exceptions.ConflictError) as e,
        ):
            crud.create_follower(user_id=1, target_user_id=2, db=mock_db)
        assert e.value.status_code == 409
        mock_db.rollback.assert_called_once()

    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_sqlalchemy_error(self, mock_get_follow, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m

        mock_get_follow.return_value = None
        mock_db.commit.side_effect = SQLAlchemyError("db error")

        with (
            patch.object(crud.followers_models, "Follower", return_value=MagicMock(spec=m.Follower)),
            pytest.raises(core_exceptions.ProcessingError) as e,
        ):
            crud.create_follower(user_id=1, target_user_id=2, db=mock_db)
        assert e.value.status_code == 500
        mock_db.rollback.assert_called_once()


class TestAcceptFollower:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m

        accept_follow = MagicMock(spec=m.Follower, id=1, follower_id=2, followee_id=1, status="pending")
        mock_db.scalars.return_value.first.return_value = accept_follow

        crud.accept_follower(user_id=1, target_user_id=2, db=mock_db)
        assert accept_follow.status == "accepted"
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once_with(accept_follow)

    def test_not_found(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.first.return_value = None
        with pytest.raises(core_exceptions.NotFoundError) as e:
            crud.accept_follower(user_id=1, target_user_id=999, db=mock_db)
        assert e.value.status_code == 404

    def test_sqlalchemy_error(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m

        accept_follow = MagicMock(spec=m.Follower, id=1, status="pending")
        mock_db.scalars.return_value.first.return_value = accept_follow
        mock_db.commit.side_effect = SQLAlchemyError("db error")

        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.accept_follower(user_id=1, target_user_id=2, db=mock_db)
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
        with pytest.raises(core_exceptions.NotFoundError) as e:
            crud.delete_follower(user_id=1, target_user_id=999, db=mock_db)
        assert e.value.status_code == 404
        mock_db.rollback.assert_called_once()

    def test_db_error(self, mock_db):
        import modules.followers.crud as crud

        mock_db.execute.side_effect = SQLAlchemyError("err")
        with pytest.raises(core_exceptions.ProcessingError) as e:
            crud.delete_follower(user_id=1, target_user_id=2, db=mock_db)
        assert e.value.status_code == 500
