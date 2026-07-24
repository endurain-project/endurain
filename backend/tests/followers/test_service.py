"""Tests for the followers service write orchestration."""

from unittest.mock import MagicMock, patch


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


class TestUnfollowUser:
    @patch("modules.followers.service.followers_crud")
    def test_deletes(self, mock_crud):
        from modules.followers.service import unfollow_user

        db = MagicMock()
        unfollow_user(1, 2, db)

        mock_crud.delete_follower.assert_called_once_with(1, 2, db)


class TestRemoveFollower:
    @patch("modules.followers.service.followers_crud")
    def test_deletes_reversed(self, mock_crud):
        from modules.followers.service import remove_follower

        db = MagicMock()
        # remove_follower(user_id=1, follower_user_id=2) removes 2's follow of 1.
        remove_follower(1, 2, db)

        mock_crud.delete_follower.assert_called_once_with(2, 1, db)


class TestListAcceptedFolloweeIds:
    @patch("modules.followers.service.followers_crud")
    def test_delegates_to_crud(self, mock_crud):
        from modules.followers.service import list_accepted_followee_ids

        db = MagicMock()
        mock_crud.list_accepted_followee_ids.return_value = [2, 3]

        result = list_accepted_followee_ids(1, db)

        assert result == [2, 3]
        mock_crud.list_accepted_followee_ids.assert_called_once_with(1, db)
