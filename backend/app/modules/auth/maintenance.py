"""Auth-owned maintenance tasks for scheduler integration.

This module collects maintenance jobs for auth packages whose cleanup remains
part of the auth composition boundary.

Each name below is the exact callable scheduled by the auth job collection.
"""

from modules.auth.identity_provider_link_tokens.scheduled_jobs import (
    delete_expired_tokens_from_db as delete_idp_link_expired_tokens_from_db,
)
from modules.auth.oauth_state.scheduled_jobs import delete_expired_oauth_states_from_db
from modules.auth.rotated_refresh_tokens.scheduled_jobs import cleanup_expired_rotated_tokens
from modules.auth.sessions.scheduled_jobs import cleanup_idle_sessions

__all__ = [
    "cleanup_expired_rotated_tokens",
    "cleanup_idle_sessions",
    "delete_expired_oauth_states_from_db",
    "delete_idp_link_expired_tokens_from_db",
]
