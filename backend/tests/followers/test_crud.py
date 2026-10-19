from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions


class TestGetAllFollowersByUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m
        from modules.followers.schema import FollowRelationshipRead

        f = MagicMock(spec=m.Follower, follower_id=2, followee_id=1, status="accepted")
        mock_db.scalars.return_value.all.return_value = [f]
        r = crud.get_all_followers_by_user_id(user_id=1, db=mock_db)
        assert r == [FollowRelationshipRead(follower_id=2, followee_id=1, status="accepted")]

    def test_empty(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_all_followers_by_user_id(user_id=1, db=mock_db)
        assert r == []


class TestGetAllFollowingByUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m
        from modules.followers.schema import FollowRelationshipRead

        f = MagicMock(spec=m.Follower, follower_id=1, followee_id=2, status="accepted")
        mock_db.scalars.return_value.all.return_value = [f]
        r = crud.get_all_following_by_user_id(user_id=1, db=mock_db)
        assert r == [FollowRelationshipRead(follower_id=1, followee_id=2, status="accepted")]

    def test_empty(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_all_following_by_user_id(user_id=1, db=mock_db)
        assert r == []


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


class TestGetFollowerForUserIdAndTargetUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m
        from modules.followers.schema import FollowRelationshipRead

        f = MagicMock(spec=m.Follower, follower_id=1, followee_id=2, status="pending")
        mock_db.scalars.return_value.first.return_value = f
        r = crud.get_follower_for_user_id_and_target_user_id(user_id=1, target_user_id=2, db=mock_db)
        assert r == FollowRelationshipRead(follower_id=1, followee_id=2, status="pending")

    def test_not_found(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.first.return_value = None
        r = crud.get_follower_for_user_id_and_target_user_id(user_id=1, target_user_id=999, db=mock_db)
        assert r is None


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


class TestFolloweeIdsAreMemoizedPerSession:
    """One request asks this repeatedly; the answer cannot change underneath it.

    A paginated activity list resolves it once for the page and again for the
    matching total, and an activity detail page asks once more per child resource
    through the visibility gate.
    """

    @staticmethod
    def _session(followee_ids):
        # ``Session.info`` is a real dict on a real session; the shared mock_db
        # fixture answers with a MagicMock, which would never register a hit.
        db = MagicMock(spec=Session)
        db.info = {}
        db.scalars.return_value.all.return_value = followee_ids
        return db

    def test_the_second_call_does_not_query(self):
        import modules.followers.crud as crud

        db = self._session([2, 3])

        assert crud.list_accepted_followee_ids(1, db) == [2, 3]
        assert crud.list_accepted_followee_ids(1, db) == [2, 3]
        assert db.scalars.call_count == 1

    def test_each_user_is_cached_separately(self):
        import modules.followers.crud as crud

        db = self._session([2, 3])
        crud.list_accepted_followee_ids(1, db)
        crud.list_accepted_followee_ids(2, db)

        assert db.scalars.call_count == 2

    def test_a_write_makes_the_next_read_see_it(self):
        """Accept-then-read on one session must not answer from the stale list."""
        import modules.followers.crud as crud

        db = self._session([2])
        assert crud.list_accepted_followee_ids(1, db) == [2]

        crud._invalidate_followee_cache(db)
        db.scalars.return_value.all.return_value = [2, 3]

        assert crud.list_accepted_followee_ids(1, db) == [2, 3]
        assert db.scalars.call_count == 2

    def test_the_cache_does_not_leak_across_sessions(self):
        import modules.followers.crud as crud

        first = self._session([2])
        second = self._session([9])

        assert crud.list_accepted_followee_ids(1, first) == [2]
        assert crud.list_accepted_followee_ids(1, second) == [9]


class TestCreateFollower:
    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_success(self, mock_get_follow, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m
        from modules.followers.schema import FollowRelationshipRead

        mock_get_follow.return_value = None
        new_follow = MagicMock(spec=m.Follower, follower_id=1, followee_id=2, status="pending")
        mock_db.refresh.side_effect = lambda x: None

        with patch.object(crud.followers_models, "Follower", return_value=new_follow):
            r = crud.create_follower(user_id=1, target_user_id=2, db=mock_db)
        assert r == FollowRelationshipRead(follower_id=1, followee_id=2, status="pending")
        mock_db.add.assert_called_once_with(new_follow)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

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
        mock_db.flush.side_effect = IntegrityError(
            "stmt", "params", Exception("UNIQUE constraint failed: followers.follower_id, followers.followee_id")
        )

        with (
            patch.object(crud.followers_models, "Follower", return_value=MagicMock(spec=m.Follower)),
            pytest.raises(core_exceptions.ConflictError) as e,
        ):
            crud.create_follower(user_id=1, target_user_id=2, db=mock_db)
        assert e.value.status_code == 409
        # The transaction owner rolls back, not persistence.
        mock_db.rollback.assert_not_called()

    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_a_target_user_that_does_not_exist_is_not_found_not_a_conflict(self, mock_get_follow, mock_db):
        """The foreign key to ``users`` fails, which is not "relationship already exists"."""
        import modules.followers.crud as crud
        import modules.followers.models as m

        mock_get_follow.return_value = None
        mock_db.flush.side_effect = IntegrityError(
            "stmt", "params", Exception('insert or update on table "followers" violates foreign key constraint')
        )

        with (
            patch.object(crud.followers_models, "Follower", return_value=MagicMock(spec=m.Follower)),
            pytest.raises(core_exceptions.NotFoundError) as e,
        ):
            crud.create_follower(user_id=1, target_user_id=999, db=mock_db)
        assert e.value.status_code == 404


class TestAcceptFollower:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m

        accept_follow = MagicMock(spec=m.Follower, id=1, follower_id=2, followee_id=1, status="accepted")
        mock_db.execute.return_value.scalars.return_value.first.return_value = accept_follow

        crud.accept_follower(user_id=1, target_user_id=2, db=mock_db)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()
        mock_db.refresh.assert_called_once_with(accept_follow)

    def test_not_found(self, mock_db):
        import modules.followers.crud as crud

        mock_db.execute.return_value.scalars.return_value.first.return_value = None
        with pytest.raises(core_exceptions.NotFoundError) as e:
            crud.accept_follower(user_id=1, target_user_id=999, db=mock_db)
        assert e.value.status_code == 404


class TestDeleteFollower:
    def test_success(self, mock_db):
        import modules.followers.crud as crud

        r = MagicMock()
        r.rowcount = 1
        mock_db.execute.return_value = r
        crud.delete_follower(user_id=1, target_user_id=2, db=mock_db)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_not_found(self, mock_db):
        import modules.followers.crud as crud

        r = MagicMock()
        r.rowcount = 0
        mock_db.execute.return_value = r
        with pytest.raises(core_exceptions.NotFoundError) as e:
            crud.delete_follower(user_id=1, target_user_id=999, db=mock_db)
        assert e.value.status_code == 404
        mock_db.flush.assert_not_called()
        mock_db.rollback.assert_not_called()


class TestAcceptIsAtomic:
    """Against a real session: the accept is one conditional UPDATE."""

    def test_the_second_accept_of_a_request_finds_nothing_to_accept(self):
        import modules.followers.crud as crud
        from tests._helpers.db import create_sqlite_session

        db = create_sqlite_session()
        try:
            crud.create_follower(2, 1, db)

            first = crud.accept_follower(user_id=1, target_user_id=2, db=db)
            assert first.status == "accepted"

            # What a concurrent second request would do; it must not be a second success.
            with pytest.raises(core_exceptions.NotFoundError):
                crud.accept_follower(user_id=1, target_user_id=2, db=db)
        finally:
            db.close()
            db.bind.dispose()
