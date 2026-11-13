"""Tests for the operations the password-reset-token module publishes to other packages."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

import modules.auth.password_reset_tokens.integration_service as password_reset_integration
import modules.auth.password_reset_tokens.models as password_reset_models
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID
from tests._helpers.db import create_sqlite_session, ensure_user


@pytest.fixture
def db():
    session = create_sqlite_session()
    factory = sessionmaker(bind=session.get_bind())
    ensure_user(factory, MOCK_USER_ID)
    ensure_user(factory, OTHER_USER_ID)
    yield session
    session.close()


_MINE = uuid.UUID(int=1)
_OTHER = uuid.UUID(int=2)


def _add_token(db, token_id, user_id, *, used=False):
    now = datetime.now(UTC)
    db.add(
        password_reset_models.PasswordResetToken(
            id=token_id,
            user_id=user_id,
            token_hash=f"hash-{token_id.hex}",
            created_at=now,
            expires_at=now + timedelta(hours=1),
            used=used,
        )
    )
    db.commit()


def _used(db, token_id):
    db.expire_all()
    return db.get(password_reset_models.PasswordResetToken, token_id).used


def test_revoke_unused_tokens_voids_only_that_users_tokens(db):
    _add_token(db, _MINE, MOCK_USER_ID)
    _add_token(db, _OTHER, OTHER_USER_ID)

    password_reset_integration.revoke_unused_tokens(MOCK_USER_ID, db)
    db.commit()

    assert _used(db, _MINE) is True
    assert _used(db, _OTHER) is False
