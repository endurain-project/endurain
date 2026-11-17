"""Tests for password-reset-token persistence operations."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import modules.auth.password_reset_tokens.crud as password_reset_crud
import modules.auth.password_reset_tokens.schema as password_reset_schema
from tests._helpers.auth import MOCK_USER_ID


def test_create_token_stages_row_without_committing(mock_db):
    now = datetime.now(UTC)
    token = password_reset_schema.PasswordResetToken(
        id=str(uuid4()),
        user_id=MOCK_USER_ID,
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
    mock_db.execute.return_value.scalar_one_or_none.return_value = MOCK_USER_ID

    user_id = password_reset_crud.claim_password_reset_token("hash", mock_db)

    assert user_id == MOCK_USER_ID
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_usable_token_lookup_is_read_only_and_matches_the_claim_conditions(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = MOCK_USER_ID

    assert password_reset_crud.get_usable_password_reset_token_user_id("hash", mock_db) == MOCK_USER_ID

    mock_db.flush.assert_not_called()
    mock_db.commit.assert_not_called()
    stmt = str(mock_db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": False}))
    assert stmt.lstrip().upper().startswith("SELECT")
    assert "used" in stmt and "expires_at" in stmt


def test_usable_token_lookup_is_none_when_nothing_matches(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    assert password_reset_crud.get_usable_password_reset_token_user_id("hash", mock_db) is None
