"""Tests for staged IdP link-token persistence operations."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import modules.auth.identity_provider_link_tokens.crud as idp_link_token_crud
import modules.auth.identity_provider_link_tokens.models as idp_link_token_models
import modules.auth.identity_provider_link_tokens.schema as idp_link_token_schema


def _token(**overrides):
    values = {
        "id": str(uuid4()),
        "token_hash": "a" * 64,
        "user_id": 1,
        "idp_id": 2,
        "created_at": datetime.now(UTC),
        "expires_at": datetime.now(UTC) + timedelta(seconds=30),
        "used": False,
        "ip_address": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_get_live_token_returns_read_schema(mock_db):
    token = idp_link_token_models.IdpLinkToken(**vars(_token()))
    mock_db.execute.return_value.scalar_one_or_none.return_value = token
    result = idp_link_token_crud.get_idp_link_token_by_hash(token.token_hash, mock_db)
    assert result == idp_link_token_schema.IdpLinkTokenRead.model_validate(token)


def test_missing_live_token_returns_none(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    assert idp_link_token_crud.get_idp_link_token_by_hash("a" * 64, mock_db) is None


def test_create_token_stages_and_returns_schema(mock_db):
    data = idp_link_token_schema.IdpLinkTokenCreate(**vars(_token()))
    token = _token()
    with patch(
        "modules.auth.identity_provider_link_tokens.crud.idp_link_token_models.IdpLinkToken", return_value=token
    ):
        result = idp_link_token_crud.create_idp_link_token(data, mock_db)
    assert result.id == token.id
    mock_db.add.assert_called_once_with(token)
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_mark_token_as_used_stages_conditional_update(mock_db):
    mock_db.execute.return_value.rowcount = 1
    assert idp_link_token_crud.mark_token_as_used("a" * 64, mock_db) is True
    mock_db.commit.assert_not_called()


def test_delete_expired_tokens_stages_and_returns_count(mock_db):
    mock_db.execute.return_value.rowcount = 2
    assert idp_link_token_crud.delete_expired_tokens(datetime.now(UTC), 100, mock_db) == 2
    mock_db.commit.assert_not_called()
