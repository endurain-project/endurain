"""Tests for pure OAuth-state generation and its cleanup job."""

from unittest.mock import patch

import modules.auth.oauth_state.scheduled_jobs as oauth_state_jobs
import modules.auth.oauth_state.utils as oauth_state_utils


def test_create_state_id_and_nonce_returns_distinct_random_values():
    state_id, nonce = oauth_state_utils.create_state_id_and_nonce()
    assert len(state_id) >= 32
    assert len(nonce) >= 32
    assert state_id != nonce


def test_cleanup_job_commits_staged_deletions():
    with (
        patch("modules.auth.oauth_state.scheduled_jobs.SessionLocal") as session_local,
        patch(
            "modules.auth.oauth_state.scheduled_jobs.oauth_state_service.delete_expired_oauth_states", return_value=2
        ),
    ):
        db = session_local.return_value.__enter__.return_value
        oauth_state_jobs.delete_expired_oauth_states_from_db()
    db.commit.assert_called_once()


def test_oauth_state_cleanup_runs_every_five_minutes():
    assert oauth_state_jobs.recurring_jobs()[0].minutes == 5
