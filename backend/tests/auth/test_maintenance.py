"""Auth maintenance stays with its owning token and session packages."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import func, select

import core.database as core_database
import modules.auth.identity_provider_link_tokens.crud as idp_link_token_crud
import modules.auth.identity_provider_link_tokens.models as idp_link_token_models
import modules.auth.identity_provider_link_tokens.scheduled_jobs as idp_link_jobs
import modules.auth.identity_provider_link_tokens.service as idp_link_token_service
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.crud as oauth_state_crud
import modules.auth.oauth_state.models as oauth_state_models
import modules.auth.oauth_state.scheduled_jobs as oauth_state_jobs
import modules.auth.oauth_state.service as oauth_state_service
import modules.auth.password_reset_tokens.crud as password_reset_crud
import modules.auth.password_reset_tokens.models as password_reset_models
import modules.auth.password_reset_tokens.scheduled_jobs as password_reset_jobs
import modules.auth.password_reset_tokens.service as password_reset_service
import modules.auth.rotated_refresh_tokens.crud as rotated_token_crud
import modules.auth.rotated_refresh_tokens.models as rotated_token_models
import modules.auth.rotated_refresh_tokens.scheduled_jobs as rotated_token_jobs
import modules.auth.rotated_refresh_tokens.service as rotated_token_service
import modules.auth.sessions.crud as sessions_crud
import modules.auth.sessions.models as sessions_models
import modules.auth.sessions.scheduled_jobs as sessions_jobs
import modules.auth.sessions.service as sessions_service
import modules.auth.sign_up_tokens.crud as sign_up_crud
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.scheduled_jobs as sign_up_jobs
import modules.auth.sign_up_tokens.service as sign_up_service
from tests._helpers.db import create_sqlite_session


def test_token_and_session_packages_publish_cleanup_jobs():
    """Each state-owning package publishes its recurring cleanup job."""
    modules = (idp_link_jobs, oauth_state_jobs, password_reset_jobs, rotated_token_jobs, sessions_jobs, sign_up_jobs)
    assert all(module.recurring_jobs() for module in modules)


def _oauth_state(key: str, expires_at: datetime) -> Any:
    return oauth_state_models.OAuthState(
        id=key,
        nonce="n",
        client_type="web",
        expires_at=expires_at,
        purpose=oauth_state_constants.OAuthStatePurpose.LOGIN,
    )


def _password_reset(key: str, expires_at: datetime) -> Any:
    return password_reset_models.PasswordResetToken(
        id=key, user_id=1, token_hash=key, created_at=expires_at, expires_at=expires_at
    )


def _sign_up(key: str, expires_at: datetime) -> Any:
    return sign_up_models.SignUpToken(id=key, user_id=1, token_hash=key, created_at=expires_at, expires_at=expires_at)


def _idp_link(key: str, expires_at: datetime) -> Any:
    return idp_link_token_models.IdpLinkToken(id=key, token_hash=key, user_id=1, idp_id=1, expires_at=expires_at)


def _session(key: str, at: datetime, *, column: str) -> Any:
    fresh = datetime.now(UTC) + timedelta(days=1)
    times = {"last_activity_at": fresh, "expires_at": fresh, column: at}
    return sessions_models.UsersSessions(
        id=key,
        user_id=1,
        ip_address="127.0.0.1",
        device_type="PC",
        operating_system="Linux",
        operating_system_version="1",
        browser="Firefox",
        browser_version="1",
        created_at=at,
        token_family_id=key,
        **times,
    )


def _rotated(key: str, refresh_token_exp: datetime) -> Any:
    return rotated_token_models.RotatedRefreshToken(
        token_family_id=key,
        hashed_token=key,
        rotation_count=0,
        rotated_at=refresh_token_exp,
        expires_at=refresh_token_exp,
        refresh_token_exp=refresh_token_exp,
    )


_PURGES: list[tuple[str, type, Callable[[str, datetime], Any], Callable[..., int]]] = [
    ("oauth_state", oauth_state_models.OAuthState, _oauth_state, oauth_state_crud.delete_expired_oauth_states),
    (
        "password_reset",
        password_reset_models.PasswordResetToken,
        _password_reset,
        password_reset_crud.delete_expired_password_reset_tokens,
    ),
    ("sign_up", sign_up_models.SignUpToken, _sign_up, sign_up_crud.delete_expired_sign_up_tokens),
    ("idp_link", idp_link_token_models.IdpLinkToken, _idp_link, idp_link_token_crud.delete_expired_tokens),
    (
        "expired_session",
        sessions_models.UsersSessions,
        lambda key, at: _session(key, at, column="expires_at"),
        sessions_crud.delete_expired_sessions,
    ),
    (
        "idle_session",
        sessions_models.UsersSessions,
        lambda key, at: _session(key, at, column="last_activity_at"),
        sessions_crud.delete_idle_sessions,
    ),
    ("rotated_token", rotated_token_models.RotatedRefreshToken, _rotated, rotated_token_crud.delete_expired_tokens),
]


@pytest.mark.parametrize(("model", "row", "purge"), [p[1:] for p in _PURGES], ids=[p[0] for p in _PURGES])
def test_a_purge_deletes_at_most_one_batch_of_past_rows(model, row, purge):
    """Each call stages one bounded batch, so the job's transaction never holds a long lock."""
    db = create_sqlite_session()
    now = datetime.now(UTC)
    db.add_all(
        [
            row("past-1", now - timedelta(hours=1)),
            row("past-2", now - timedelta(hours=2)),
            row("live", now + timedelta(hours=1)),
        ]
    )
    db.commit()

    assert purge(now, 1, db) == 1
    assert purge(now, 1, db) == 1
    assert purge(now, 1, db) == 0
    assert db.execute(select(func.count()).select_from(model)).scalar_one() == 1
    db.close()


_SERVICE_PURGES = [
    (
        oauth_state_service,
        "oauth_state_crud.delete_expired_oauth_states",
        lambda db: oauth_state_service.delete_expired_oauth_states(db),
    ),
    (
        password_reset_service,
        "password_reset_crud.delete_expired_password_reset_tokens",
        lambda db: password_reset_service.delete_expired_password_reset_tokens(db),
    ),
    (
        sign_up_service,
        "sign_up_crud.delete_expired_sign_up_tokens",
        lambda db: sign_up_service.delete_expired_sign_up_tokens(db),
    ),
    (
        idp_link_token_service,
        "idp_link_token_crud.delete_expired_tokens",
        lambda db: idp_link_token_service.delete_expired_tokens(db),
    ),
    (
        sessions_service,
        "sessions_crud.delete_expired_sessions",
        lambda db: sessions_service.delete_expired_sessions(db),
    ),
    (
        rotated_token_service,
        "rotated_token_crud.delete_expired_tokens",
        lambda db: rotated_token_service.delete_expired_tokens(datetime.now(UTC), db),
    ),
]


@pytest.mark.parametrize(("service", "crud_call", "purge"), _SERVICE_PURGES, ids=lambda v: getattr(v, "__name__", None))
def test_a_purge_commits_each_batch_until_one_comes_back_short(service, crud_call, purge):
    db = MagicMock()
    with patch(f"{service.__name__}.{crud_call}", side_effect=[core_database.PURGE_BATCH_SIZE, 3]) as stage:
        assert purge(db) == core_database.PURGE_BATCH_SIZE + 3
    assert stage.call_count == 2
    assert all(c.args[-2:] == (core_database.PURGE_BATCH_SIZE, db) for c in stage.call_args_list)
    assert db.commit.call_count == 2


class TestSessionPurge:
    """Expired sessions are dead whatever the idle policy, so they are always removed."""

    @patch("modules.auth.sessions.service.server_settings_integration.get_session_policy")
    @patch("modules.auth.sessions.service.sessions_crud")
    def test_expired_sessions_go_with_the_idle_timeout_off(self, mock_crud, mock_policy):
        mock_policy.return_value = MagicMock(idle_timeout=None)
        mock_crud.delete_expired_sessions.return_value = 2
        db = MagicMock()

        assert sessions_service.delete_expired_sessions(db) == 2
        assert sessions_service.delete_idle_sessions(db) == 0
        mock_crud.delete_idle_sessions.assert_not_called()
        db.commit.assert_called_once()

    @patch("modules.auth.sessions.service.server_settings_integration.get_session_policy")
    @patch("modules.auth.sessions.service.sessions_crud")
    def test_idle_sessions_go_past_the_configured_timeout(self, mock_crud, mock_policy):
        mock_policy.return_value = MagicMock(idle_timeout=timedelta(minutes=30))
        mock_crud.delete_idle_sessions.return_value = 4
        before = datetime.now(UTC)

        assert sessions_service.delete_idle_sessions(MagicMock()) == 4
        cutoff = mock_crud.delete_idle_sessions.call_args.args[0]
        assert before - timedelta(minutes=30, seconds=5) < cutoff <= datetime.now(UTC) - timedelta(minutes=30)

    @patch("modules.auth.sessions.scheduled_jobs.sessions_service")
    @patch("modules.auth.sessions.scheduled_jobs.SessionLocal")
    def test_the_job_runs_both_purges(self, mock_session_local, mock_service):
        mock_service.delete_expired_sessions.return_value = 1
        mock_service.delete_idle_sessions.return_value = 0

        sessions_jobs.delete_stale_sessions()

        mock_service.delete_expired_sessions.assert_called_once()
        mock_service.delete_idle_sessions.assert_called_once()
