"""Tests for the followers service write orchestration."""

import uuid
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest

_ID_1 = uuid.uuid4()
_ID_2 = uuid.uuid4()
_ID_3 = uuid.uuid4()
_ID_4 = uuid.uuid4()
_ID_6 = uuid.uuid4()
_ID_8 = uuid.uuid4()


class TestNetworkPrivacy:
    @pytest.mark.parametrize("method_name", ["list_followers", "list_following"])
    @patch("modules.followers.service.followers_crud")
    def test_non_owner_can_only_read_accepted_relationships(self, mock_crud, method_name):
        from modules.followers import service
        from modules.followers.schema import FollowRelationshipRead

        db = MagicMock()
        mock_crud.get_follower_for_user_id_and_target_user_id.return_value = FollowRelationshipRead(
            follower_id=_ID_1,
            followee_id=_ID_2,
            status="accepted",
        )
        mock_crud.get_all_followers_by_user_id.return_value = []
        mock_crud.get_all_following_by_user_id.return_value = []
        mock_crud.count_followers_by_user_id.return_value = 0
        mock_crud.count_following_by_user_id.return_value = 0

        getattr(service, method_name)(_ID_2, _ID_1, db, accepted_only=False)

        list_method = getattr(
            mock_crud,
            "get_all_followers_by_user_id" if method_name == "list_followers" else "get_all_following_by_user_id",
        )
        count_method = getattr(
            mock_crud,
            "count_followers_by_user_id" if method_name == "list_followers" else "count_following_by_user_id",
        )
        assert list_method.call_args.kwargs["accepted_only"] is True
        assert count_method.call_args.kwargs["accepted_only"] is True

    @patch("modules.followers.service.followers_crud")
    def test_profile_counts_include_only_accepted_relationships(self, mock_crud):
        from modules.followers import service
        from modules.followers.schema import FollowRelationshipRead

        mock_crud.get_follower_for_user_id_and_target_user_id.return_value = FollowRelationshipRead(
            follower_id=_ID_1,
            followee_id=_ID_2,
            status="accepted",
        )
        mock_crud.count_followers_by_user_id.return_value = 12
        mock_crud.count_following_by_user_id.return_value = 8
        db = MagicMock()

        counts = service.get_profile_follow_counts(_ID_2, _ID_1, db)

        assert (counts.followers, counts.following) == (12, 8)
        mock_crud.count_followers_by_user_id.assert_called_once_with(_ID_2, db, accepted_only=True)
        mock_crud.count_following_by_user_id.assert_called_once_with(_ID_2, db, accepted_only=True)

    @patch("modules.followers.service.followers_crud")
    def test_profile_counts_are_absent_when_the_network_is_private(self, mock_crud):
        from modules.followers import service

        mock_crud.get_follower_for_user_id_and_target_user_id.return_value = None

        counts = service.get_profile_follow_counts(_ID_2, _ID_1, MagicMock())

        assert counts is None
        mock_crud.count_followers_by_user_id.assert_not_called()
        mock_crud.count_following_by_user_id.assert_not_called()

    @patch("modules.followers.service.followers_crud")
    def test_owner_can_include_pending_relationships(self, mock_crud):
        from modules.followers import service

        db = MagicMock()
        mock_crud.get_all_followers_by_user_id.return_value = []
        mock_crud.count_followers_by_user_id.return_value = 0

        service.list_followers(_ID_1, _ID_1, db, accepted_only=False)

        assert mock_crud.get_all_followers_by_user_id.call_args.kwargs["accepted_only"] is False
        assert mock_crud.count_followers_by_user_id.call_args.kwargs["accepted_only"] is False


def _profile(user_id: uuid.UUID):
    from modules.users.users.schema import UserPublicRead

    return UserPublicRead(id=user_id, name=f"User {user_id}", username=f"user{user_id}")


class TestListsCarryTheOtherUsersProfile:
    """Every row's other side arrives with the page, so the client needs no lookup per row."""

    @patch("modules.followers.service.users_integration")
    @patch("modules.followers.service.followers_crud")
    def test_followers_are_looked_up_by_follower_id(self, mock_crud, mock_users):
        from modules.followers import service
        from modules.followers.schema import FollowRelationshipRead

        mock_crud.get_all_followers_by_user_id.return_value = [
            FollowRelationshipRead(follower_id=_ID_3, followee_id=_ID_1, status="accepted"),
            FollowRelationshipRead(follower_id=_ID_4, followee_id=_ID_1, status="pending"),
        ]
        mock_crud.count_followers_by_user_id.return_value = 2
        mock_users.list_public_profiles.return_value = {_ID_3: _profile(_ID_3), _ID_4: _profile(_ID_4)}
        db = MagicMock()

        page = service.list_followers(_ID_1, _ID_1, db)

        mock_users.list_public_profiles.assert_called_once_with({_ID_3, _ID_4}, db)
        assert set(page.users) == {_ID_3, _ID_4}
        assert page.users[_ID_3].name == f"User {_ID_3}"

    @patch("modules.followers.service.users_integration")
    @patch("modules.followers.service.followers_crud")
    def test_following_are_looked_up_by_followee_id(self, mock_crud, mock_users):
        from modules.followers import service
        from modules.followers.schema import FollowRelationshipRead

        mock_crud.get_all_following_by_user_id.return_value = [
            FollowRelationshipRead(follower_id=_ID_1, followee_id=_ID_8, status="accepted"),
        ]
        mock_crud.count_following_by_user_id.return_value = 1
        mock_users.list_public_profiles.return_value = {_ID_8: _profile(_ID_8)}
        db = MagicMock()

        page = service.list_following(_ID_1, _ID_1, db)

        mock_users.list_public_profiles.assert_called_once_with({_ID_8}, db)
        assert set(page.users) == {_ID_8}

    @patch("modules.followers.service.users_integration")
    @patch("modules.followers.service.followers_crud")
    def test_pending_requests_are_looked_up_by_requester_id(self, mock_crud, mock_users):
        from modules.followers import service
        from modules.followers.schema import FollowRelationshipRead

        mock_crud.get_pending_requests_for_user_id.return_value = [
            FollowRelationshipRead(follower_id=_ID_6, followee_id=_ID_1, status="pending"),
        ]
        mock_crud.is_blocked.return_value = False
        mock_crud.get_last_decline_at.return_value = None
        mock_crud.count_pending_requests_for_user_id.return_value = 1
        mock_users.list_public_profiles.return_value = {_ID_6: _profile(_ID_6)}
        db = MagicMock()

        page = service.list_pending_requests(_ID_1, db)

        mock_users.list_public_profiles.assert_called_once_with({_ID_6}, db)
        assert set(page.users) == {_ID_6}

    @patch("modules.followers.service.users_integration")
    @patch("modules.followers.service.followers_crud")
    def test_a_user_without_a_profile_has_no_entry(self, mock_crud, mock_users):
        from modules.followers import service
        from modules.followers.schema import FollowRelationshipRead

        mock_crud.get_all_followers_by_user_id.return_value = [
            FollowRelationshipRead(follower_id=_ID_3, followee_id=_ID_1, status="accepted"),
        ]
        mock_crud.count_followers_by_user_id.return_value = 1
        mock_users.list_public_profiles.return_value = {}

        page = service.list_followers(_ID_1, _ID_1, MagicMock())

        assert page.users == {}
        assert [item.follower_id for item in page.items] == [_ID_3]

    @patch("modules.followers.service.users_integration")
    @patch("modules.followers.service.followers_crud")
    def test_the_envelope_is_unchanged_apart_from_the_users(self, mock_crud, mock_users):
        from modules.followers import service
        from modules.followers.schema import FollowRelationshipRead

        mock_crud.get_all_followers_by_user_id.return_value = [
            FollowRelationshipRead(follower_id=_ID_3, followee_id=_ID_1, status="accepted"),
        ]
        mock_crud.count_followers_by_user_id.return_value = 40
        mock_users.list_public_profiles.return_value = {_ID_3: _profile(_ID_3)}

        page = service.list_followers(_ID_1, _ID_1, MagicMock(), page_number=1, num_records=25)

        assert (page.total, page.page, page.num_records, page.next) == (40, 1, 25, 2)


class TestFollowUser:
    @patch("modules.followers.service.users_integration")
    @patch("modules.followers.service.followers_event_publishers")
    @patch("modules.followers.service.followers_crud")
    def test_creates_and_publishes(self, mock_crud, mock_pub, mock_users):
        from modules.followers.schema import FollowRelationshipRead
        from modules.followers.service import follow_user

        db = MagicMock()
        mock_crud.is_blocked.return_value = False
        mock_crud.get_last_decline_at.return_value = None
        mock_crud.count_pending_requests_for_user_id.return_value = 0
        mock_crud.create_follower.return_value = FollowRelationshipRead(
            follower_id=_ID_1, followee_id=_ID_2, status="pending"
        )

        result = follow_user(_ID_1, _ID_2, db)

        assert result.follower_id == _ID_1
        mock_crud.create_follower.assert_called_once_with(_ID_1, _ID_2, db)
        mock_pub.publish_follower_requested.assert_called_once_with(_ID_1, _ID_2, db, commit=db.commit)

    @patch("modules.followers.service.followers_event_publishers")
    @patch("modules.followers.service.followers_crud")
    def test_self_follow_is_refused(self, mock_crud, mock_pub):
        import core.exceptions as core_exceptions
        from modules.followers.service import follow_user

        db = MagicMock()

        with pytest.raises(core_exceptions.InvalidInputError) as e:
            follow_user(_ID_1, _ID_1, db)

        assert e.value.status_code == 400
        mock_crud.create_follower.assert_not_called()
        mock_pub.publish_follower_requested.assert_not_called()

    @patch("modules.followers.service.users_integration")
    @patch("modules.followers.service.followers_event_publishers")
    @patch("modules.followers.service.followers_crud")
    def test_a_target_with_too_many_pending_requests_is_refused(self, mock_crud, mock_pub, mock_users):
        import core.exceptions as core_exceptions
        from modules.followers.constants import MAX_PENDING_REQUESTS
        from modules.followers.service import follow_user

        db = MagicMock()
        mock_crud.is_blocked.return_value = False
        mock_crud.get_last_decline_at.return_value = None
        mock_crud.count_pending_requests_for_user_id.return_value = MAX_PENDING_REQUESTS

        with pytest.raises(core_exceptions.ConflictError) as e:
            follow_user(_ID_1, _ID_2, db)

        assert e.value.status_code == 409
        mock_crud.create_follower.assert_not_called()
        mock_pub.publish_follower_requested.assert_not_called()


class TestFollowUserHiddenTargets:
    """A target that is missing, inactive or awaiting approval answers the same not found."""

    @pytest.fixture
    def factory(self):
        from tests._helpers.db import create_sqlite_session_factory, ensure_user

        factory = create_sqlite_session_factory()
        ensure_user(factory, _ID_1)
        yield factory
        factory.kw["bind"].dispose()

    @staticmethod
    def _set_target_state(factory, state: str) -> None:
        import modules.users.users.models as users_models
        from tests._helpers.db import ensure_user

        if state == "missing":
            return
        ensure_user(factory, _ID_2)
        with factory() as db:
            user = db.get(users_models.Users, _ID_2)
            user.active = state != "inactive"
            user.pending_admin_approval = state == "pending"
            db.commit()

    @pytest.mark.parametrize("state", ["missing", "inactive", "pending"])
    @patch("modules.followers.service.followers_event_publishers")
    @patch("modules.followers.service.followers_crud")
    def test_hidden_target_is_not_found_even_when_its_pending_requests_are_full(
        self, mock_crud, mock_pub, factory, state
    ):
        import core.exceptions as core_exceptions
        from modules.followers.constants import MAX_PENDING_REQUESTS
        from modules.followers.service import follow_user

        self._set_target_state(factory, state)
        mock_crud.is_blocked.return_value = False
        mock_crud.get_last_decline_at.return_value = None
        mock_crud.count_pending_requests_for_user_id.return_value = MAX_PENDING_REQUESTS

        with factory() as db, pytest.raises(core_exceptions.NotFoundError) as e:
            follow_user(_ID_1, _ID_2, db)

        assert e.value.status_code == 404
        assert e.value.detail == "User not found"
        mock_crud.lock_pending_requests.assert_not_called()
        mock_crud.count_pending_requests_for_user_id.assert_not_called()
        mock_crud.create_follower.assert_not_called()
        mock_pub.publish_follower_requested.assert_not_called()


class TestPendingCapIsSerialised:
    @patch("modules.followers.service.users_integration")
    @patch("modules.followers.service.followers_event_publishers")
    @patch("modules.followers.service.followers_crud")
    def test_the_targets_requests_are_locked_before_they_are_counted(self, mock_crud, mock_pub, mock_users):
        from modules.followers.service import follow_user

        calls = MagicMock()
        calls.attach_mock(mock_crud.lock_pending_requests, "lock")
        calls.attach_mock(mock_crud.count_pending_requests_for_user_id, "count")
        calls.attach_mock(mock_crud.create_follower, "create")
        mock_crud.is_blocked.return_value = False
        mock_crud.get_last_decline_at.return_value = None
        mock_crud.count_pending_requests_for_user_id.return_value = 0

        follow_user(_ID_1, _ID_2, MagicMock())

        assert [call[0] for call in calls.mock_calls] == ["lock", "count", "create"]


class TestAcceptFollowRequest:
    @patch("modules.followers.service.followers_event_publishers")
    @patch("modules.followers.service.followers_crud")
    def test_accepts_and_publishes(self, mock_crud, mock_pub):
        from modules.followers.service import accept_follow_request

        db = MagicMock()
        mock_crud.count_following_by_user_id.return_value = 0
        accept_follow_request(_ID_1, _ID_2, db)

        mock_crud.accept_follower.assert_called_once_with(_ID_1, _ID_2, db)
        mock_pub.publish_follower_accepted.assert_called_once_with(_ID_1, _ID_2, db, commit=db.commit)

    @patch("modules.followers.service.followers_event_publishers")
    @patch("modules.followers.service.followers_crud")
    def test_a_follower_at_the_followee_cap_cannot_be_accepted(self, mock_crud, mock_pub):
        import core.exceptions as core_exceptions
        from modules.followers.constants import MAX_ACCEPTED_FOLLOWEES
        from modules.followers.service import accept_follow_request

        db = MagicMock()
        mock_crud.count_following_by_user_id.return_value = MAX_ACCEPTED_FOLLOWEES

        with pytest.raises(core_exceptions.ConflictError) as e:
            accept_follow_request(_ID_1, _ID_2, db)

        assert e.value.status_code == 409
        mock_crud.count_following_by_user_id.assert_called_once_with(_ID_2, db, accepted_only=True)
        mock_crud.accept_follower.assert_not_called()
        mock_pub.publish_follower_accepted.assert_not_called()

    @patch("modules.followers.service.followers_event_publishers")
    @patch("modules.followers.service.followers_crud")
    def test_the_followers_followees_are_locked_before_they_are_counted(self, mock_crud, mock_pub):
        from modules.followers.service import accept_follow_request

        calls = MagicMock()
        calls.attach_mock(mock_crud.lock_accepted_followees, "lock")
        calls.attach_mock(mock_crud.count_following_by_user_id, "count")
        calls.attach_mock(mock_crud.accept_follower, "accept")
        mock_crud.count_following_by_user_id.return_value = 0

        accept_follow_request(_ID_1, _ID_2, MagicMock())

        assert [call[0] for call in calls.mock_calls] == ["lock", "count", "accept"]
        mock_crud.lock_accepted_followees.assert_called_once()
        assert mock_crud.lock_accepted_followees.call_args.args[0] == _ID_2


class TestDeleteRelationship:
    def test_unfollowing_deletes_the_row(self):
        from modules.followers.service import delete_relationship

        db = MagicMock()
        with patch("modules.followers.service.followers_crud") as crud:
            delete_relationship(_ID_2, _ID_1, _ID_1, db)

        crud.delete_follower.assert_called_once_with(_ID_1, _ID_2, db)
        db.commit.assert_called_once()

    @pytest.mark.parametrize(
        "status,published",
        [("pending", True), ("accepted", False)],
    )
    def test_only_a_pending_request_publishes_its_removal(self, status, published):
        from modules.followers.constants import FollowStatus
        from modules.followers.service import delete_relationship

        db = MagicMock()
        with (
            patch("modules.followers.service.followers_crud") as crud,
            patch("modules.followers.service.followers_event_publishers") as pub,
        ):
            crud.delete_follower.return_value = FollowStatus(status)
            delete_relationship(_ID_2, _ID_1, _ID_1, db)

        assert pub.publish_follower_request_removed.called is published
        if published:
            pub.publish_follower_request_removed.assert_called_once_with(
                _ID_1, _ID_2, db, commit=db.commit, source="api:delete_follow_relationship"
            )
        else:
            db.commit.assert_called_once()

    def test_removing_a_follower_deletes_the_same_row(self):
        """Same row, opposite caller — the reason these are one operation."""
        from modules.followers.service import delete_relationship

        db = MagicMock()
        with patch("modules.followers.service.followers_crud") as crud:
            delete_relationship(_ID_1, _ID_2, _ID_1, db)

        crud.delete_follower.assert_called_once_with(_ID_2, _ID_1, db)

    def test_a_third_party_is_refused(self):
        import core.exceptions as core_exceptions
        from modules.followers.service import delete_relationship

        db = MagicMock()
        with (
            patch("modules.followers.service.followers_crud") as crud,
            pytest.raises(core_exceptions.NotFoundError),
        ):
            delete_relationship(_ID_2, _ID_3, _ID_1, db)

        crud.delete_follower.assert_not_called()


class TestRejectFollowRequest:
    def test_deletes_only_the_pending_row(self):
        """Declining must not double as removing an accepted follower."""
        from modules.followers.constants import FollowStatus
        from modules.followers.service import reject_follow_request

        db = MagicMock()
        with patch("modules.followers.service.followers_crud") as crud:
            reject_follow_request(_ID_1, _ID_2, db)

        crud.delete_follower.assert_called_once_with(_ID_2, _ID_1, db, status=FollowStatus.PENDING)
        db.commit.assert_called_once()

    def test_publishes_the_removal(self):
        from modules.followers.service import reject_follow_request

        db = MagicMock()
        with (
            patch("modules.followers.service.followers_crud"),
            patch("modules.followers.service.followers_event_publishers") as pub,
        ):
            reject_follow_request(_ID_1, _ID_2, db)

        pub.publish_follower_request_removed.assert_called_once_with(
            _ID_2, _ID_1, db, commit=db.commit, source="api:reject_follow_request"
        )


class TestListAcceptedFolloweeIds:
    @patch("modules.followers.integration_service.followers_crud")
    def test_delegates_to_crud(self, mock_crud):
        from modules.followers.integration_service import list_accepted_followee_ids

        db = MagicMock()
        mock_crud.list_accepted_followee_ids.return_value = [_ID_2, _ID_3]

        result = list_accepted_followee_ids(_ID_1, db)

        assert result == [_ID_2, _ID_3]
        mock_crud.list_accepted_followee_ids.assert_called_once_with(_ID_1, db)

    def test_is_not_on_the_internal_service(self):
        """The cross-module read lives on ``integration_service``, not ``service``.

        ``service`` is this module's own application layer; a consumer reaching
        into it would depend on the privacy-checked follow/accept/unfollow flows
        it has no business seeing.
        """
        import modules.followers.service as followers_service

        assert not hasattr(followers_service, "list_accepted_followee_ids")


class TestStateChangesLogAtInfo:
    @pytest.mark.parametrize(
        ("call", "message"),
        [
            (lambda s, db: s.follow_user(_ID_1, _ID_2, db), "Follow requested"),
            (lambda s, db: s.accept_follow_request(_ID_1, _ID_2, db), "Follow request accepted"),
            (lambda s, db: s.reject_follow_request(_ID_1, _ID_2, db), "Follow request rejected"),
            (lambda s, db: s.delete_relationship(_ID_2, _ID_1, _ID_1, db), "Deleted a follow relationship"),
        ],
    )
    @patch("modules.followers.service.users_integration")
    @patch("modules.followers.service.followers_event_publishers")
    @patch("modules.followers.service.followers_crud")
    def test_a_completed_change_is_logged_once_at_info(self, mock_crud, _mock_pub, _mock_users, call, message, caplog):
        from modules.followers import service

        mock_crud.is_blocked.return_value = False
        mock_crud.get_last_decline_at.return_value = None
        mock_crud.count_pending_requests_for_user_id.return_value = 0
        mock_crud.count_following_by_user_id.return_value = 0

        with caplog.at_level("DEBUG", logger=service.logger.name):
            call(service, MagicMock())

        assert [(record.levelname, record.getMessage()) for record in caplog.records] == [("INFO", message)]


class TestFollowAudit:
    @patch("modules.followers.service.followers_event_publishers")
    @patch("modules.followers.service.followers_crud")
    def test_accepting_a_request_is_audited_with_the_follower_as_target(self, mock_crud, mock_pub):
        from modules.followers.audit_actions import FOLLOW_ACCEPT
        from modules.followers.service import accept_follow_request

        mock_crud.count_following_by_user_id.return_value = 0
        with jasil_testing.capture_audit() as audit:
            accept_follow_request(_ID_1, _ID_2, MagicMock())

        entry = audit.assert_audited(
            FOLLOW_ACCEPT.id, target_type="user", target_id=str(_ID_2), target_owner_id=str(_ID_1)
        )
        assert entry.details is None

    @patch("modules.followers.service.followers_event_publishers")
    @patch("modules.followers.service.followers_crud")
    def test_a_refused_acceptance_is_not_audited(self, mock_crud, mock_pub):
        import core.exceptions as core_exceptions
        from modules.followers.audit_actions import FOLLOW_ACCEPT
        from modules.followers.constants import MAX_ACCEPTED_FOLLOWEES
        from modules.followers.service import accept_follow_request

        mock_crud.count_following_by_user_id.return_value = MAX_ACCEPTED_FOLLOWEES
        with jasil_testing.capture_audit() as audit, pytest.raises(core_exceptions.ConflictError):
            accept_follow_request(_ID_1, _ID_2, MagicMock())

        audit.assert_not_audited(FOLLOW_ACCEPT.id)

    @pytest.mark.parametrize(
        "followee_id,follower_id,caller",
        [(_ID_2, _ID_1, _ID_1), (_ID_1, _ID_2, _ID_1)],
        ids=["follower unfollows", "followed user removes the follower"],
    )
    @patch("modules.followers.service.followers_event_publishers")
    @patch("modules.followers.service.followers_crud")
    def test_removing_an_accepted_relationship_is_audited_from_either_side(
        self, mock_crud, mock_pub, followee_id, follower_id, caller
    ):
        from modules.followers.audit_actions import FOLLOW_REMOVE
        from modules.followers.constants import FollowStatus
        from modules.followers.service import delete_relationship

        mock_crud.delete_follower.return_value = FollowStatus.ACCEPTED
        with jasil_testing.capture_audit() as audit:
            delete_relationship(followee_id, follower_id, caller, MagicMock())

        entry = audit.assert_audited(
            FOLLOW_REMOVE.id,
            target_type="user",
            target_id=str(follower_id),
            target_owner_id=str(followee_id),
        )
        assert entry.details is None

    @patch("modules.followers.service.followers_event_publishers")
    @patch("modules.followers.service.followers_crud")
    def test_deleting_a_pending_request_is_not_audited(self, mock_crud, mock_pub):
        from modules.followers.audit_actions import FOLLOW_REMOVE
        from modules.followers.constants import FollowStatus
        from modules.followers.service import delete_relationship

        mock_crud.delete_follower.return_value = FollowStatus.PENDING
        with jasil_testing.capture_audit() as audit:
            delete_relationship(_ID_2, _ID_1, _ID_1, MagicMock())

        audit.assert_not_audited(FOLLOW_REMOVE.id)

    @patch("modules.followers.service.followers_event_publishers")
    @patch("modules.followers.service.followers_crud")
    def test_declining_a_request_is_not_audited(self, mock_crud, mock_pub):
        from modules.followers.audit_actions import FOLLOW_REMOVE
        from modules.followers.service import reject_follow_request

        with jasil_testing.capture_audit() as audit:
            reject_follow_request(_ID_1, _ID_2, MagicMock())

        audit.assert_not_audited(FOLLOW_REMOVE.id)

    @patch("modules.followers.service.users_integration")
    @patch("modules.followers.service.followers_event_publishers")
    @patch("modules.followers.service.followers_crud")
    def test_creating_a_request_is_not_audited(self, mock_crud, mock_pub, mock_users):
        from modules.followers.service import follow_user

        mock_crud.is_blocked.return_value = False
        mock_crud.get_last_decline_at.return_value = None
        mock_crud.count_pending_requests_for_user_id.return_value = 0
        with jasil_testing.capture_audit() as audit:
            follow_user(_ID_1, _ID_2, MagicMock())

        assert audit.entries == []
