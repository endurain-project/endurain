"""Tests for session transaction and lifecycle orchestration."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.sessions.contracts as sessions_contracts
import modules.auth.sessions.service as sessions_service

_FIREFOX_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"


def _session(**updates):
    data = {
        "id": "session-id",
        "user_id": 7,
        "refresh_token": "hashed-refresh",
        "ip_address": "127.0.0.1",
        "device_type": "PC",
        "operating_system": "Linux",
        "operating_system_version": "1",
        "browser": "Firefox",
        "browser_version": "1",
        "created_at": datetime.now(UTC),
        "last_activity_at": datetime.now(UTC),
        "expires_at": datetime.now(UTC) + timedelta(days=1),
        "oauth_state_id": None,
        "tokens_exchanged": False,
        "token_family_id": "family-id",
        "rotation_count": 0,
        "last_rotation_at": None,
        "csrf_token_hash": None,
    }
    data.update(updates)
    return sessions_contracts.SessionRead(**data)


def test_create_session_hashes_secrets_and_stages(mock_db):
    user = SimpleNamespace(id=7)
    hasher = MagicMock()
    hasher.hash_password.return_value = "hashed-refresh"
    with (
        patch("modules.auth.sessions.service.sessions_crud.create_session", return_value=_session()) as create,
    ):
        result = sessions_service.create_session(
            "session-id",
            user,
            "127.0.0.1",
            _FIREFOX_UA,
            "plain-refresh",
            hasher,
            datetime.now(UTC) + timedelta(days=1),
            mock_db,
        )
    assert result.id == "session-id"
    hasher.hash_password.assert_called_once_with("plain-refresh")
    assert create.call_args.args[0].refresh_token == "hashed-refresh"
    assert create.call_args.args[0].ip_address == "127.0.0.1"
    assert create.call_args.args[0].browser == "Firefox"
    assert create.call_args.args[0].device_type == "PC"
    mock_db.commit.assert_not_called()


def test_edit_session_stages_rotation(mock_db):
    session = _session()
    hasher = MagicMock()
    hasher.hash_password.return_value = "replacement-hash"
    with (
        patch(
            "modules.auth.sessions.service.sessions_crud.edit_session", return_value=_session(rotation_count=1)
        ) as edit,
    ):
        result = sessions_service.edit_session(
            session, "127.0.0.2", _FIREFOX_UA, "replacement", hasher, datetime.now(UTC) + timedelta(days=1), mock_db
        )
    assert result.rotation_count == 1
    assert edit.call_args.args[0].refresh_token == "replacement-hash"
    assert edit.call_args.args[0].rotation_count == 1
    assert edit.call_args.args[0].ip_address == "127.0.0.2"
    mock_db.commit.assert_not_called()


def test_session_with_oauth_state_uses_integration_surface(mock_db):
    with (
        patch(
            "modules.auth.sessions.service.sessions_crud.get_session_by_id_not_expired",
            return_value=_session(oauth_state_id="state-id"),
        ),
        patch(
            "modules.auth.sessions.service.oauth_state_integration.get_oauth_state_by_id_not_expired",
            return_value="state",
        ) as get_state,
    ):
        result = sessions_service.get_session_with_oauth_state("session-id", mock_db)
    assert result is not None
    assert result[0].id == "session-id"
    assert result[1] == "state"
    get_state.assert_called_once_with("state-id", mock_db)


def test_claim_token_exchange_cleans_up_oauth_and_stages(mock_db):
    with (
        patch(
            "modules.auth.sessions.service.sessions_crud.get_session_by_id",
            return_value=_session(oauth_state_id="state-id"),
        ),
        patch("modules.auth.sessions.service.sessions_crud.claim_session_for_token_exchange", return_value=True),
        patch("modules.auth.sessions.service.sessions_crud.clear_oauth_state_reference") as clear_reference,
        patch("modules.auth.sessions.service.oauth_state_integration.delete_oauth_state") as delete_state,
    ):
        assert sessions_service.claim_session_for_token_exchange("session-id", "hashed", mock_db) is True
    clear_reference.assert_called_once_with("session-id", mock_db)
    delete_state.assert_called_once_with("state-id", mock_db)
    mock_db.commit.assert_not_called()


def test_claim_lost_race_does_not_commit(mock_db):
    with (
        patch("modules.auth.sessions.service.sessions_crud.get_session_by_id", return_value=_session()),
        patch("modules.auth.sessions.service.sessions_crud.claim_session_for_token_exchange", return_value=False),
    ):
        assert sessions_service.claim_session_for_token_exchange("session-id", "hash", mock_db) is False
    mock_db.commit.assert_not_called()


def test_delete_session_cleans_linked_records_and_commits(mock_db):
    session = _session(oauth_state_id="state-id")
    with (
        patch("modules.auth.sessions.service.sessions_crud.delete_session", return_value=session),
        patch("modules.auth.sessions.service.oauth_state_integration.delete_oauth_state") as delete_state,
        patch("modules.auth.sessions.service.rotated_refresh_tokens_integration.delete_by_family") as delete_family,
    ):
        sessions_service.delete_session("session-id", 7, mock_db)
    delete_state.assert_called_once_with("state-id", mock_db)
    delete_family.assert_called_once_with("family-id", mock_db)
    mock_db.commit.assert_called_once()


def test_family_invalidation_stages_session_and_token_deletion(mock_db):
    with (
        patch("modules.auth.sessions.service.sessions_crud.delete_sessions_by_family", return_value=2),
        patch("modules.auth.sessions.service.rotated_refresh_tokens_integration.delete_by_family", return_value=4),
    ):
        assert sessions_service.invalidate_token_family("family-id", mock_db) == 2
    mock_db.commit.assert_not_called()


def test_stage_delete_session_cleans_linked_records_without_committing(mock_db):
    session = _session(oauth_state_id="state-id")
    with (
        patch("modules.auth.sessions.service.sessions_crud.delete_session", return_value=session),
        patch("modules.auth.sessions.service.oauth_state_integration.delete_oauth_state") as delete_state,
        patch("modules.auth.sessions.service.rotated_refresh_tokens_integration.delete_by_family") as delete_family,
    ):
        sessions_service.stage_delete_session("session-id", 7, mock_db)
    delete_state.assert_called_once_with("state-id", mock_db)
    delete_family.assert_called_once_with("family-id", mock_db)
    mock_db.commit.assert_not_called()


def test_delete_user_sessions_stages_without_committing(mock_db):
    with patch("modules.auth.sessions.service.sessions_crud.delete_sessions_by_user", return_value=3):
        assert sessions_service.delete_sessions_by_user(7, mock_db, "current") == 3
    mock_db.commit.assert_not_called()


def test_delete_user_sessions_standalone_commits(mock_db):
    with patch("modules.auth.sessions.service.sessions_crud.delete_sessions_by_user", return_value=3):
        assert sessions_service.delete_sessions_by_user_and_commit(7, mock_db) == 3
    mock_db.commit.assert_called_once()


def test_missing_session_deletion_propagates_domain_not_found(mock_db):
    with (
        patch(
            "modules.auth.sessions.service.sessions_crud.delete_session",
            side_effect=core_exceptions.NotFoundError("Session not found"),
        ),
        pytest.raises(core_exceptions.NotFoundError),
    ):
        sessions_service.delete_session("missing", 7, mock_db)
    mock_db.commit.assert_not_called()


def test_list_user_sessions_builds_a_page_from_the_window_and_count(mock_db):
    page = core_pagination.PageParams(2, 1)
    with (
        patch("modules.auth.sessions.service.core_config.settings") as settings,
        patch("modules.auth.sessions.service.sessions_crud.get_user_sessions_page", return_value=[_session()]) as rows,
        patch("modules.auth.sessions.service.sessions_crud.count_user_sessions", return_value=3) as count,
    ):
        settings.ENVIRONMENT = "production"
        result = sessions_service.list_user_sessions(7, page, mock_db)
    rows.assert_called_once_with(7, mock_db, limit=1, offset=1)
    count.assert_called_once_with(7, mock_db)
    assert [item.id for item in result.items] == ["session-id"]
    assert (result.total, result.page, result.next) == (3, 2, 3)
    assert not hasattr(result.items[0], "refresh_token")


def test_list_user_sessions_is_empty_in_demo(mock_db):
    with (
        patch("modules.auth.sessions.service.core_config.settings") as settings,
        patch("modules.auth.sessions.service.sessions_crud.get_user_sessions_page") as rows,
    ):
        settings.ENVIRONMENT = "demo"
        result = sessions_service.list_user_sessions(7, core_pagination.PageParams(1, 25), mock_db)
    rows.assert_not_called()
    assert result.items == [] and result.total == 0


def test_session_logs_carry_a_fingerprint_not_the_session_id(mock_db, caplog):
    with (
        caplog.at_level("INFO"),
        patch("modules.auth.sessions.service.sessions_crud.delete_session", return_value=_session()),
        patch("modules.auth.sessions.service.rotated_refresh_tokens_integration.delete_by_family"),
    ):
        sessions_service.delete_session("secret-session-id", 7, mock_db)
    assert "secret-session-id" not in caplog.text
    assert "secret-session-id" not in str([record.__dict__ for record in caplog.records])
