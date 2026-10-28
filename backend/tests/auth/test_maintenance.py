"""Tests for auth.maintenance's remaining scheduled-work exports."""

import modules.auth.identity_provider_link_tokens.scheduled_jobs as idp_link_jobs
import modules.auth.maintenance as auth_maintenance
import modules.auth.oauth_state.scheduled_jobs as oauth_state_jobs
import modules.auth.rotated_refresh_tokens.scheduled_jobs as rotated_token_jobs
import modules.auth.sessions.scheduled_jobs as sessions_jobs


def test_remaining_exports_point_to_their_owning_jobs():
    """Auth maintenance keeps aliases only for the jobs it still aggregates."""
    assert auth_maintenance.cleanup_expired_rotated_tokens is rotated_token_jobs.cleanup_expired_rotated_tokens
    assert auth_maintenance.cleanup_idle_sessions is sessions_jobs.cleanup_idle_sessions
    assert auth_maintenance.delete_expired_oauth_states_from_db is oauth_state_jobs.delete_expired_oauth_states_from_db
    assert auth_maintenance.delete_idp_link_expired_tokens_from_db is idp_link_jobs.delete_expired_tokens_from_db
