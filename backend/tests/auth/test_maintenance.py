"""Tests for auth.maintenance's remaining scheduled-work exports."""

import modules.auth.maintenance as auth_maintenance


class TestMaintenanceContract:
    """The auth maintenance exports preserve the source callables."""

    def test_all_exports_are_present_and_callable(self):
        for name in auth_maintenance.__all__:
            assert hasattr(auth_maintenance, name), f"missing maintenance export: {name}"
            assert callable(getattr(auth_maintenance, name)), f"export not callable: {name}"

    def test_reexports_point_to_underlying_callables(self):
        from modules.auth.identity_provider_link_tokens.scheduled_jobs import (
            delete_expired_tokens_from_db as delete_idp_link_expired_tokens_from_db,
        )
        from modules.auth.oauth_state.scheduled_jobs import delete_expired_oauth_states_from_db
        from modules.auth.password_reset_tokens.utils import (
            delete_invalid_tokens_from_db as src_delete_password_reset,
        )
        from modules.auth.rotated_refresh_tokens.scheduled_jobs import cleanup_expired_rotated_tokens
        from modules.auth.sessions.scheduled_jobs import cleanup_idle_sessions
        from modules.auth.sign_up_tokens.utils import (
            delete_invalid_tokens_from_db as src_delete_sign_up,
        )

        assert auth_maintenance.cleanup_expired_rotated_tokens is cleanup_expired_rotated_tokens
        assert auth_maintenance.cleanup_idle_sessions is cleanup_idle_sessions
        assert auth_maintenance.delete_expired_oauth_states_from_db is delete_expired_oauth_states_from_db
        assert auth_maintenance.delete_idp_link_expired_tokens_from_db is delete_idp_link_expired_tokens_from_db
        assert auth_maintenance.delete_invalid_password_reset_tokens_from_db is src_delete_password_reset
        assert auth_maintenance.delete_invalid_sign_up_tokens_from_db is src_delete_sign_up
