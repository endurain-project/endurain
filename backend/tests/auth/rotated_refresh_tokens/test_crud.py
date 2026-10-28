"""Tests for staged rotated-token persistence."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.rotated_refresh_tokens.crud as rotated_token_crud
import modules.auth.rotated_refresh_tokens.schema as rotated_token_schema
from tests._helpers.db import create_sqlite_session


def _token(**overrides):
    values = {
        "id": 3,
        "token_family_id": "f" * 36,
        "hashed_token": "a" * 64,
        "rotation_count": 1,
        "rotated_at": datetime.now(UTC),
        "expires_at": datetime.now(UTC) + timedelta(seconds=30),
        "replacement_refresh_token": "encrypted",
        "replacement_refresh_token_exp": datetime.now(UTC) + timedelta(days=1),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_get_rotated_token_returns_read_schema(mock_db):
    token = _token()
    mock_db.execute.return_value.scalar_one_or_none.return_value = token
    assert rotated_token_crud.get_rotated_token_by_hash(token.hashed_token, mock_db) == (
        rotated_token_schema.RotatedRefreshTokenRead.model_validate(token)
    )


def test_create_rotated_token_stages_row(mock_db):
    values = _token().__dict__.copy()
    values.pop("id")
    data = rotated_token_schema.RotatedRefreshTokenCreate(**values)
    token = _token()
    with patch("modules.auth.rotated_refresh_tokens.crud.rotated_token_models.RotatedRefreshToken", return_value=token):
        result = rotated_token_crud.create_rotated_token(data, mock_db)
    assert result.id == token.id
    mock_db.add.assert_called_once_with(token)
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_rotating_the_same_token_twice_is_a_conflict():
    """The unique hash is what decides which of two concurrent refreshes rotates the token."""
    db = create_sqlite_session()
    values = _token().__dict__.copy()
    values.pop("id")
    data = rotated_token_schema.RotatedRefreshTokenCreate(**values)
    rotated_token_crud.create_rotated_token(data, db)

    with pytest.raises(core_exceptions.ConflictError):
        rotated_token_crud.create_rotated_token(data, db)

    db.close()


def test_delete_operations_stage_and_return_row_counts(mock_db):
    mock_db.execute.return_value.rowcount = 2
    assert rotated_token_crud.delete_expired_tokens(datetime.now(UTC), mock_db) == 2
    assert rotated_token_crud.delete_by_family("f" * 36, mock_db) == 2
    assert mock_db.flush.call_count == 2
    mock_db.commit.assert_not_called()
