"""The profile photo flows a router delegates to."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

import modules.users.users_profile.photo_service as profile_photo_service

_USER_ID = uuid.UUID(int=11)


class TestSetPhoto:
    @pytest.mark.parametrize("replaced", [False, True])
    @patch("modules.users.users_profile.photo_service.users_integration")
    def test_returns_the_servable_url_and_whether_a_photo_was_replaced(self, mock_users, replaced):
        mock_users.upload_user_photo.return_value = replaced
        mock_users.require_user.return_value = MagicMock(photo_path="/users/x/photo?t=1")
        file, storage, db = MagicMock(), MagicMock(), MagicMock()

        photo, was_replaced = profile_photo_service.set_photo(_USER_ID, file, storage, db)

        assert was_replaced is replaced
        assert photo.photo_path == "/users/x/photo?t=1"
        mock_users.upload_user_photo.assert_called_once_with(_USER_ID, file, storage, db)
        mock_users.require_user.assert_called_once_with(_USER_ID, db)


class TestDeletePhoto:
    @patch("modules.users.users_profile.photo_service.users_integration")
    def test_clears_the_photo(self, mock_users):
        storage, db = MagicMock(), MagicMock()

        profile_photo_service.delete_photo(_USER_ID, storage, db)

        mock_users.delete_user_photo.assert_called_once_with(_USER_ID, storage, db)
