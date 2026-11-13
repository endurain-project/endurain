import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
from modules.followers.constants import FollowStatus

_ID_1 = uuid.uuid4()
_ID_2 = uuid.uuid4()
_ID_3 = uuid.uuid4()
_ID_9 = uuid.uuid4()
_ID_999 = uuid.uuid4()


class TestGetAllFollowersByUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m
        from modules.followers.schema import FollowRelationshipRead

        f = MagicMock(spec=m.Follower, follower_id=_ID_2, followee_id=_ID_1, status="accepted")
        mock_db.scalars.return_value.all.return_value = [f]
        r = crud.get_all_followers_by_user_id(user_id=_ID_1, db=mock_db)
        assert r == [FollowRelationshipRead(follower_id=_ID_2, followee_id=_ID_1, status="accepted")]

    def test_empty(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_all_followers_by_user_id(user_id=_ID_1, db=mock_db)
        assert r == []


class TestGetAllFollowingByUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m
        from modules.followers.schema import FollowRelationshipRead

        f = MagicMock(spec=m.Follower, follower_id=_ID_1, followee_id=_ID_2, status="accepted")
        mock_db.scalars.return_value.all.return_value = [f]
        r = crud.get_all_following_by_user_id(user_id=_ID_1, db=mock_db)
        assert r == [FollowRelationshipRead(follower_id=_ID_1, followee_id=_ID_2, status="accepted")]

    def test_empty(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        r = crud.get_all_following_by_user_id(user_id=_ID_1, db=mock_db)
        assert r == []


class TestCountFollowersByUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalar.return_value = 10
        r = crud.count_followers_by_user_id(user_id=_ID_1, db=mock_db)
        assert r == 10

    def test_success_accepted_only(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalar.return_value = 5
        r = crud.count_followers_by_user_id(user_id=_ID_1, db=mock_db, accepted_only=True)
        assert r == 5

    def test_none_returns_zero(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalar.return_value = None
        r = crud.count_followers_by_user_id(user_id=_ID_1, db=mock_db)
        assert r == 0


class TestCountFollowingByUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalar.return_value = 8
        r = crud.count_following_by_user_id(user_id=_ID_1, db=mock_db)
        assert r == 8

    def test_success_accepted_only(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalar.return_value = 3
        r = crud.count_following_by_user_id(user_id=_ID_1, db=mock_db, accepted_only=True)
        assert r == 3

    def test_none_returns_zero(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalar.return_value = None
        r = crud.count_following_by_user_id(user_id=_ID_1, db=mock_db)
        assert r == 0


class TestGetFollowerForUserIdAndTargetUserId:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m
        from modules.followers.schema import FollowRelationshipRead

        f = MagicMock(spec=m.Follower, follower_id=_ID_1, followee_id=_ID_2, status="pending")
        mock_db.scalars.return_value.first.return_value = f
        r = crud.get_follower_for_user_id_and_target_user_id(user_id=_ID_1, target_user_id=_ID_2, db=mock_db)
        assert r == FollowRelationshipRead(follower_id=_ID_1, followee_id=_ID_2, status="pending")

    def test_not_found(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.first.return_value = None
        r = crud.get_follower_for_user_id_and_target_user_id(user_id=_ID_1, target_user_id=_ID_999, db=mock_db)
        assert r is None


class TestListAcceptedFolloweeIds:
    def test_success(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.all.return_value = [_ID_2, _ID_3]
        r = crud.list_accepted_followee_ids(user_id=_ID_1, db=mock_db)
        assert r == [_ID_2, _ID_3]

    def test_empty(self, mock_db):
        import modules.followers.crud as crud

        mock_db.scalars.return_value.all.return_value = []
        assert crud.list_accepted_followee_ids(user_id=_ID_1, db=mock_db) == []


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

        db = self._session([_ID_2, _ID_3])

        assert crud.list_accepted_followee_ids(_ID_1, db) == [_ID_2, _ID_3]
        assert crud.list_accepted_followee_ids(_ID_1, db) == [_ID_2, _ID_3]
        assert db.scalars.call_count == 1

    def test_each_user_is_cached_separately(self):
        import modules.followers.crud as crud

        db = self._session([_ID_2, _ID_3])
        crud.list_accepted_followee_ids(_ID_1, db)
        crud.list_accepted_followee_ids(_ID_2, db)

        assert db.scalars.call_count == 2

    def test_a_write_makes_the_next_read_see_it(self):
        """Accept-then-read on one session must not answer from the stale list."""
        import modules.followers.crud as crud

        db = self._session([_ID_2])
        assert crud.list_accepted_followee_ids(_ID_1, db) == [_ID_2]

        crud._invalidate_followee_cache(db)
        db.scalars.return_value.all.return_value = [_ID_2, _ID_3]

        assert crud.list_accepted_followee_ids(_ID_1, db) == [_ID_2, _ID_3]
        assert db.scalars.call_count == 2

    def test_the_cache_does_not_leak_across_sessions(self):
        import modules.followers.crud as crud

        first = self._session([_ID_2])
        second = self._session([_ID_9])

        assert crud.list_accepted_followee_ids(_ID_1, first) == [_ID_2]
        assert crud.list_accepted_followee_ids(_ID_1, second) == [_ID_9]


class TestCreateFollower:
    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_success(self, mock_get_follow, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m
        from modules.followers.schema import FollowRelationshipRead

        mock_get_follow.return_value = None
        new_follow = MagicMock(spec=m.Follower, follower_id=_ID_1, followee_id=_ID_2, status="pending")
        mock_db.refresh.side_effect = lambda x: None

        with patch.object(crud.followers_models, "Follower", return_value=new_follow):
            r = crud.create_follower(user_id=_ID_1, target_user_id=_ID_2, db=mock_db)
        assert r == FollowRelationshipRead(follower_id=_ID_1, followee_id=_ID_2, status="pending")
        mock_db.add.assert_called_once_with(new_follow)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    @patch("modules.followers.crud.get_follower_for_user_id_and_target_user_id")
    def test_already_exists(self, mock_get_follow, mock_db):
        import modules.followers.crud as crud

        mock_get_follow.return_value = MagicMock()
        with pytest.raises(core_exceptions.ConflictError) as e:
            crud.create_follower(user_id=_ID_1, target_user_id=_ID_2, db=mock_db)
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
            crud.create_follower(user_id=_ID_1, target_user_id=_ID_2, db=mock_db)
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
            crud.create_follower(user_id=_ID_1, target_user_id=_ID_999, db=mock_db)
        assert e.value.status_code == 404


class TestAcceptFollower:
    def test_success(self, mock_db):
        import modules.followers.crud as crud
        import modules.followers.models as m

        accept_follow = MagicMock(spec=m.Follower, id=_ID_1, follower_id=_ID_2, followee_id=_ID_1, status="accepted")
        mock_db.execute.return_value.scalars.return_value.first.return_value = accept_follow

        crud.accept_follower(user_id=_ID_1, target_user_id=_ID_2, db=mock_db)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()
        mock_db.refresh.assert_called_once_with(accept_follow)

    def test_not_found(self, mock_db):
        import modules.followers.crud as crud

        mock_db.execute.return_value.scalars.return_value.first.return_value = None
        with pytest.raises(core_exceptions.NotFoundError) as e:
            crud.accept_follower(user_id=_ID_1, target_user_id=_ID_999, db=mock_db)
        assert e.value.status_code == 404


class TestDeleteFollower:
    def test_success(self, mock_db):
        import modules.followers.crud as crud

        mock_db.execute.return_value.scalar_one_or_none.return_value = "pending"
        deleted = crud.delete_follower(user_id=_ID_1, target_user_id=_ID_2, db=mock_db)
        assert deleted == FollowStatus.PENDING
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_not_found(self, mock_db):
        import modules.followers.crud as crud

        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        with pytest.raises(core_exceptions.NotFoundError) as e:
            crud.delete_follower(user_id=_ID_1, target_user_id=_ID_999, db=mock_db)
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
            crud.create_follower(_ID_2, _ID_1, db)

            first = crud.accept_follower(user_id=_ID_1, target_user_id=_ID_2, db=db)
            assert first.status == "accepted"

            # What a concurrent second request would do; it must not be a second success.
            with pytest.raises(core_exceptions.NotFoundError):
                crud.accept_follower(user_id=_ID_1, target_user_id=_ID_2, db=db)
        finally:
            db.close()
            db.bind.dispose()


class TestFollowerListOrder:
    def test_followers_and_following_list_by_creation_time(self):
        from datetime import UTC, datetime, timedelta

        import modules.followers.crud as crud
        import modules.followers.models as m
        from tests._helpers.db import create_sqlite_session_factory, ensure_user

        factory = create_sqlite_session_factory()
        for user_id in (_ID_1, _ID_2, _ID_3):
            ensure_user(factory, user_id)
        now = datetime.now(UTC)
        # The older row has the larger id: the order follows the creation time.
        rows = [(_ID_2, _ID_1, now - timedelta(hours=1), uuid.UUID(int=2)), (_ID_3, _ID_1, now, uuid.UUID(int=1))]
        with factory() as db:
            for follower_id, followee_id, created_at, row_id in rows:
                db.add(
                    m.Follower(
                        id=row_id,
                        follower_id=follower_id,
                        followee_id=followee_id,
                        status="accepted",
                        created_at=created_at,
                    )
                )
            db.commit()
            followers = crud.get_all_followers_by_user_id(user_id=_ID_1, db=db)
        factory.kw["bind"].dispose()

        assert [row.follower_id for row in followers] == [_ID_2, _ID_3]


class TestAdvisoryLocks:
    def test_the_lock_is_keyed_by_the_hash_of_the_users_id(self, mock_db):
        import modules.followers.crud as crud

        crud.lock_pending_requests(_ID_1, mock_db)

        statement, params = mock_db.execute.call_args.args
        assert "hashtext(:user_id)" in str(statement)
        assert params == {"namespace": 7301, "user_id": str(_ID_1)}
