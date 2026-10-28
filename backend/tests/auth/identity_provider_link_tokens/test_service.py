"""Tests for IdP link-token generation and scheduled cleanup."""

from datetime import UTC, datetime
from unittest.mock import patch

import modules.auth.identity_provider_link_tokens.scheduled_jobs as idp_link_token_jobs
import modules.auth.identity_provider_link_tokens.service as idp_link_token_service


def test_hash_idp_link_token_is_sha256_hex():
    result = idp_link_token_service.hash_idp_link_token("secret")
    assert len(result) == 64
    assert result == idp_link_token_service.hash_idp_link_token("secret")


def test_generate_token_stages_record_and_returns_raw_value(mock_db):
    now = datetime.now(UTC)
    with (
        patch("modules.auth.identity_provider_link_tokens.service.secrets.token_urlsafe", return_value="raw-token"),
        patch("modules.auth.identity_provider_link_tokens.service.datetime") as mocked_datetime,
        patch(
            "modules.auth.identity_provider_link_tokens.service.idp_link_token_crud.create_idp_link_token",
            return_value=type("Token", (), {"expires_at": now})(),
        ),
    ):
        mocked_datetime.now.return_value = now
        response = idp_link_token_service.generate_idp_link_token(3, 4, None, mock_db)
    assert response.token == "raw-token"
    assert response.expires_at == now
    mock_db.commit.assert_not_called()


def test_recurring_job_cleans_up_expired_tokens():
    jobs = idp_link_token_jobs.recurring_jobs()
    assert len(jobs) == 1
    assert jobs[0].minutes == 5
