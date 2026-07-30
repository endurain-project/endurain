"""Tests for the followers service write orchestration."""

from unittest.mock import MagicMock, patch

import pytest


class TestNetworkPrivacy:
    @pytest.mark.parametrize("method_name", ["list_followers", "list_following"])
    @patch("modules.followers.service.followers_crud")
    def test_non_owner_can_only_read_accepted_relationships(self, mock_crud, method_name):
        from modules.followers import service
        from modules.followers.schema import FollowRelationship

        db = MagicMock()
        mock_crud.get_follower_for_user_id_and_target_user_id.return_value = FollowRelationship(
            follower_id=1,
            followee_id=2,
            status="accepted",
        )
        mock_crud.get_all_followers_by_user_id.return_value = []
        mock_crud.get_all_following_by_user_id.return_value = []
        mock_crud.count_followers_by_user_id.return_value = 0
        mock_crud.count_following_by_user_id.return_value = 0

        getattr(service, method_name)(2, 1, db, accepted_only=False)

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
    def test_owner_can_include_pending_relationships(self, mock_crud):
        from modules.followers import service

        db = MagicMock()
        mock_crud.get_all_followers_by_user_id.return_value = []
        mock_crud.count_followers_by_user_id.return_value = 0

        service.list_followers(1, 1, db, accepted_only=False)

        assert mock_crud.get_all_followers_by_user_id.call_args.kwargs["accepted_only"] is False
        assert mock_crud.count_followers_by_user_id.call_args.kwargs["accepted_only"] is False


class TestFollowUser:
    @patch("modules.followers.service.followers_event_publishers")
    @patch("modules.followers.service.followers_crud")
    def test_creates_and_publishes(self, mock_crud, mock_pub):
        from modules.followers.schema import FollowRelationship
        from modules.followers.service import follow_user

        db = MagicMock()
        mock_crud.create_follower.return_value = FollowRelationship(follower_id=1, followee_id=2, status="pending")

        result = follow_user(1, 2, db)

        assert result.follower_id == 1
        mock_crud.create_follower.assert_called_once_with(1, 2, db)
        mock_pub.publish_follower_requested.assert_called_once_with(1, 2, db)


class TestAcceptFollowRequest:
    @patch("modules.followers.service.followers_event_publishers")
    @patch("modules.followers.service.followers_crud")
    def test_accepts_and_publishes(self, mock_crud, mock_pub):
        from modules.followers.service import accept_follow_request

        db = MagicMock()
        accept_follow_request(1, 2, db)

        mock_crud.accept_follower.assert_called_once_with(1, 2, db)
        mock_pub.publish_follower_accepted.assert_called_once_with(1, 2, db)


class TestDeleteRelationship:
    def test_unfollowing_deletes_the_row(self):
        from modules.followers.service import delete_relationship

        db = MagicMock()
        with patch("modules.followers.service.followers_crud") as crud:
            delete_relationship(2, 1, 1, db)

        crud.delete_follower.assert_called_once_with(1, 2, db)

    def test_removing_a_follower_deletes_the_same_row(self):
        """Same row, opposite caller — the reason these are one operation."""
        from modules.followers.service import delete_relationship

        db = MagicMock()
        with patch("modules.followers.service.followers_crud") as crud:
            delete_relationship(1, 2, 1, db)

        crud.delete_follower.assert_called_once_with(2, 1, db)

    def test_a_third_party_is_refused(self):
        import core.exceptions as core_exceptions
        from modules.followers.service import delete_relationship

        db = MagicMock()
        with (
            patch("modules.followers.service.followers_crud") as crud,
            pytest.raises(core_exceptions.PermissionDeniedError),
        ):
            delete_relationship(2, 3, 1, db)

        crud.delete_follower.assert_not_called()


class TestRejectFollowRequest:
    def test_deletes_the_pending_row(self):
        from modules.followers.service import reject_follow_request

        db = MagicMock()
        with patch("modules.followers.service.followers_crud") as crud:
            reject_follow_request(1, 2, db)

        crud.delete_follower.assert_called_once_with(2, 1, db)


class TestListAcceptedFolloweeIds:
    @patch("modules.followers.integration_service.followers_crud")
    def test_delegates_to_crud(self, mock_crud):
        from modules.followers.integration_service import list_accepted_followee_ids

        db = MagicMock()
        mock_crud.list_accepted_followee_ids.return_value = [2, 3]

        result = list_accepted_followee_ids(1, db)

        assert result == [2, 3]
        mock_crud.list_accepted_followee_ids.assert_called_once_with(1, db)

    def test_is_not_on_the_internal_service(self):
        """The cross-module read lives on ``integration_service``, not ``service``.

        ``service`` is this module's own application layer; a consumer reaching
        into it would depend on the privacy-checked follow/accept/unfollow flows
        it has no business seeing.
        """
        import modules.followers.service as followers_service

        assert not hasattr(followers_service, "list_accepted_followee_ids")
