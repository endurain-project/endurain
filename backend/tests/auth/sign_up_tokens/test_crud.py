"""Tests for sign-up-token persistence operations."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import sessionmaker

import modules.auth.sign_up_tokens.crud as sign_up_crud
import modules.auth.sign_up_tokens.schema as sign_up_schema
from tests._helpers.db import create_sqlite_session, ensure_user


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

    deleted = sign_up_crud.delete_expired_sign_up_tokens(datetime.now(UTC), 100, mock_db)

    assert deleted == 3
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


class TestClaimSignUpToken:
    """A link works once even when two requests present it together, so the claim is one UPDATE."""

    @staticmethod
    def _db_with_token(
        *,
        expires_in: timedelta = timedelta(hours=1),
        used: bool = False,
        email: str | None = None,
        previous_email: str | None = None,
    ):
        db = create_sqlite_session()
        ensure_user(sessionmaker(bind=db.get_bind()), 7)
        now = datetime.now(UTC)
        sign_up_crud.create_sign_up_token(
            sign_up_schema.SignUpToken(
                id="token-1",
                user_id=7,
                token_hash="hash",
                created_at=now,
                expires_at=now + expires_in,
                used=used,
                email=email,
                previous_email=previous_email,
            ),
            db,
        )
        return db

    def test_a_valid_token_is_claimed_once(self):
        db = self._db_with_token()

        claim = sign_up_crud.claim_sign_up_token("hash", db)

        assert claim is not None
        assert (claim.id, claim.user_id) == ("token-1", 7)
        assert sign_up_crud.claim_sign_up_token("hash", db) is None

    def test_the_claim_carries_the_tokens_addresses(self):
        db = self._db_with_token(email="new@example.com", previous_email="old@example.com")

        claim = sign_up_crud.claim_sign_up_token("hash", db)

        assert (claim.email, claim.previous_email) == ("new@example.com", "old@example.com")

    def test_an_expired_token_is_not_claimed(self):
        db = self._db_with_token(expires_in=timedelta(hours=-1))

        assert sign_up_crud.claim_sign_up_token("hash", db) is None

    def test_a_used_token_is_not_claimed(self):
        db = self._db_with_token(used=True)

        assert sign_up_crud.claim_sign_up_token("hash", db) is None

    def test_an_unknown_token_is_not_claimed(self):
        db = self._db_with_token()

        assert sign_up_crud.claim_sign_up_token("other", db) is None
