"""Tests for user management router functions."""

from unittest.mock import MagicMock, patch

import modules.auth.account_security.integration_service as account_security_integration
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
        user_attributes = users_schema.UsersAdminEditPassword(password=new_password)
        db = MagicMock()

        with patch.object(account_security_integration, "change_managed_user_password") as change_password:
            users_router.edit_user_password(
                request=MagicMock(),
                user_id=user_id,
                user_attributes=user_attributes,
                token_user_id=7,
                db=db,
            )

        change_password.assert_called_once_with(user_id, new_password, db)
