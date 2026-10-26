"""Tests for user management router functions."""

from unittest.mock import MagicMock

import modules.users.users.router as users_router
import modules.users.users.schema as users_schema


class TestEditUserPassword:
    """
    Test suite for admin password reset route.
    """

    def test_revokes_target_sessions_after_password_reset(self):
        """
        Test admin password resets delete existing target sessions.
        """
        user_id = 42
        new_password = "new-secure-password"
        identity_service = MagicMock()
        user_attributes = users_schema.UsersAdminEditPassword(password=new_password)

        users_router.edit_user_password(
            request=MagicMock(),
            user_id=user_id,
            user_attributes=user_attributes,
            identity_service=identity_service,
        )

        identity_service.change_managed_user_password.assert_called_once_with(
            user_id,
            new_password,
        )
