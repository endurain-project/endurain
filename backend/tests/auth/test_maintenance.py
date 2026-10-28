"""Auth maintenance stays with its owning token and session packages."""

import modules.auth.identity_provider_link_tokens.scheduled_jobs as idp_link_jobs
import modules.auth.oauth_state.scheduled_jobs as oauth_state_jobs
import modules.auth.password_reset_tokens.scheduled_jobs as password_reset_jobs
import modules.auth.rotated_refresh_tokens.scheduled_jobs as rotated_token_jobs
import modules.auth.sessions.scheduled_jobs as sessions_jobs
import modules.auth.sign_up_tokens.scheduled_jobs as sign_up_jobs


def test_token_and_session_packages_publish_cleanup_jobs():
    """Each state-owning package publishes its recurring cleanup job."""
    modules = (idp_link_jobs, oauth_state_jobs, password_reset_jobs, rotated_token_jobs, sessions_jobs, sign_up_jobs)
    assert all(module.recurring_jobs() for module in modules)
