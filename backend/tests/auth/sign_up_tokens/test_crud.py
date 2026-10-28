"""Tests for sign-up-token persistence operations."""

from datetime import UTC, datetime

import modules.auth.sign_up_tokens.crud as sign_up_crud
import modules.auth.sign_up_tokens.schema as sign_up_schema


def test_create_token_stages_row_without_committing(mock_db):
    now = datetime.now(UTC)
    token = sign_up_schema.SignUpToken(
        id="token-id",
        user_id=7,
        token_hash="hash",
        created_at=now,
        expires_at=now,
        used=False,
    )

    state = sign_up_crud.create_sign_up_token(token, mock_db)

    mock_db.add.assert_called_once()
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()
    assert state.id == token.id
    assert state.user_id == token.user_id


def test_delete_expired_tokens_stages_delete_without_committing(mock_db):
    mock_db.execute.return_value.rowcount = 3

    deleted = sign_up_crud.delete_expired_sign_up_tokens(mock_db)

    assert deleted == 3
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()
