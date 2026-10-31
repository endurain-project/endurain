"""Tests for password-reset-token persistence operations."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import modules.auth.password_reset_tokens.crud as password_reset_crud
import modules.auth.password_reset_tokens.schema as password_reset_schema


def test_create_token_stages_row_without_committing(mock_db):
    now = datetime.now(UTC)
    token = password_reset_schema.PasswordResetToken(
        id=str(uuid4()),
        user_id=1,
        token_hash="hash",
        created_at=now,
        expires_at=now + timedelta(hours=1),
        used=False,
    )

    state = password_reset_crud.create_password_reset_token(token, mock_db)

    mock_db.add.assert_called_once()
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()
    assert state.id == token.id
    assert state.user_id == token.user_id


def test_claim_token_stages_atomic_update_without_committing(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = 42

    user_id = password_reset_crud.claim_password_reset_token("hash", mock_db)

    assert user_id == 42
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()
