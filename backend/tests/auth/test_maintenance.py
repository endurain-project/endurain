"""Tests for auth.maintenance.

``auth.maintenance`` is the single surface ``core.scheduler`` uses to run
recurring auth cleanup jobs. It re-exports lower-level ``*.utils`` callables
unchanged and defines one thin wrapper, ``cleanup_expired_pending_mfa_logins``,
which delegates to ``auth._internal.security_stores``.

These tests verify the delegation wrapper and that the public maintenance
contract (the re-exported names and ``__all__``) stays intact, since the whole
point of this module is to keep the scheduler decoupled from the scatter of
low-level auth utils modules.
"""

from unittest.mock import patch

import auth.maintenance as auth_maintenance


class TestCleanupExpiredPendingMfaLogins:
    """The wrapper delegates to auth._internal.security_stores."""

    def test_delegates_to_security_stores_and_returns_result(self):
        with patch(
            "auth.maintenance.auth_security_stores.cleanup_expired_pending_mfa_logins",
            return_value=5,
        ) as mock_cleanup:
            result = auth_maintenance.cleanup_expired_pending_mfa_logins()

        mock_cleanup.assert_called_once_with()
        assert result == 5

    def test_passes_through_none_result(self):
        with patch(
            "auth.maintenance.auth_security_stores.cleanup_expired_pending_mfa_logins",
            return_value=None,
        ) as mock_cleanup:
            result = auth_maintenance.cleanup_expired_pending_mfa_logins()

        mock_cleanup.assert_called_once_with()
        assert result is None


class TestMaintenanceContract:
    """The re-exported maintenance surface stays stable for the scheduler."""

    def test_all_exports_are_present_and_callable(self):
        for name in auth_maintenance.__all__:
            assert hasattr(auth_maintenance, name), f"missing maintenance export: {name}"
            assert callable(getattr(auth_maintenance, name)), f"export not callable: {name}"

    def test_reexports_point_to_underlying_callables(self):
        """Re-exported names must be the same objects as their source utils."""
        from auth.identity_providers.link_tokens.utils import delete_idp_link_expired_tokens_from_db
        from auth.oauth_state.utils import delete_expired_oauth_states_from_db
        from auth.password_reset_tokens.utils import (
            delete_invalid_tokens_from_db as src_delete_password_reset,
        )
        from auth.sessions.rotated_refresh_tokens.utils import cleanup_expired_rotated_tokens
        from auth.sessions.utils import cleanup_idle_sessions
        from auth.sign_up_tokens.utils import (
            delete_invalid_tokens_from_db as src_delete_sign_up,
        )

        assert auth_maintenance.cleanup_expired_rotated_tokens is cleanup_expired_rotated_tokens
        assert auth_maintenance.cleanup_idle_sessions is cleanup_idle_sessions
        assert auth_maintenance.delete_expired_oauth_states_from_db is delete_expired_oauth_states_from_db
        assert auth_maintenance.delete_idp_link_expired_tokens_from_db is delete_idp_link_expired_tokens_from_db
        assert auth_maintenance.delete_invalid_password_reset_tokens_from_db is src_delete_password_reset
        assert auth_maintenance.delete_invalid_sign_up_tokens_from_db is src_delete_sign_up
