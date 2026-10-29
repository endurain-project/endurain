"""Tests for staged OAuth-state persistence operations."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import modules.auth.oauth_state.crud as oauth_state_crud
import modules.auth.oauth_state.schema as oauth_state_schema
from tests._helpers.db import create_sqlite_session


def _state(**overrides):
    values = {
        "id": "a" * 32,
        "idp_id": 3,
        "code_challenge": None,
        "code_challenge_method": None,
        "nonce": "n" * 32,
        "redirect_path": None,
        "client_type": "web",
        "ip_address": None,
        "created_at": datetime.now(UTC),
        "expires_at": datetime.now(UTC) + timedelta(minutes=5),
        "used": False,
        "user_id": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_get_unused_state_returns_read_dto(mock_db):
    state = _state()
    mock_db.execute.return_value.scalar_one_or_none.return_value = state
    assert oauth_state_crud.get_oauth_state_by_id_and_not_used(state.id, mock_db) == (
        oauth_state_schema.OAuthStateRead.model_validate(state)
    )


def test_get_expired_or_missing_state_returns_none(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    assert oauth_state_crud.get_oauth_state_by_id_and_not_used("a" * 32, mock_db) is None


def test_create_state_stages_row_and_returns_schema(mock_db):
    state = _state()
    with (
        patch("modules.auth.oauth_state.crud.oauth_state_models.OAuthState", return_value=state),
        patch(
            "modules.auth.oauth_state.crud.oauth_state_serializers.to_read_schema",
            return_value=oauth_state_schema.OAuthStateRead.model_validate(state),
        ),
    ):
        result = oauth_state_crud.create_oauth_state(state.id, state.nonce, state.client_type, None, mock_db)
    assert result.id == state.id
    mock_db.add.assert_called_once_with(state)
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_a_link_state_keeps_the_digest_of_its_browser_binding():
    db = create_sqlite_session()

    created = oauth_state_crud.create_oauth_state(
        "s" * 32, "n" * 32, "web", None, db, user_id=7, browser_binding_hash="d" * 64, idp_code_verifier="v" * 64
    )

    assert created.browser_binding_hash == "d" * 64
    assert created.idp_code_verifier == "v" * 64
    assert oauth_state_crud.get_oauth_state_by_id_and_not_used("s" * 32, db).browser_binding_hash == "d" * 64
    db.close()


def test_mark_state_used_is_conditional_and_staged(mock_db):
    mock_db.execute.return_value.rowcount = 1
    assert oauth_state_crud.mark_oauth_state_used("a" * 32, mock_db) is True
    mock_db.commit.assert_not_called()


def test_delete_expired_states_stages_and_returns_count(mock_db):
    mock_db.execute.return_value.rowcount = 3
    assert oauth_state_crud.delete_expired_oauth_states(datetime.now(UTC), 100, mock_db) == 3
    mock_db.commit.assert_not_called()
