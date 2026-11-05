"""Tests for the operations the password-reset-token module publishes to other packages."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

import modules.auth.password_reset_tokens.integration_service as password_reset_integration
import modules.auth.password_reset_tokens.models as password_reset_models
from tests._helpers.db import create_sqlite_session, ensure_user


@pytest.fixture
def db():
    session = create_sqlite_session()
    factory = sessionmaker(bind=session.get_bind())
    ensure_user(factory, 7)
    ensure_user(factory, 8)
    yield session
    session.close()


def _add_token(db, token_id, user_id, *, used=False):
    now = datetime.now(UTC)
    db.add(
        password_reset_models.PasswordResetToken(
            id=token_id,
            user_id=user_id,
            token_hash=f"hash-{token_id}",
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
    _add_token(db, "mine", 7)
    _add_token(db, "other", 8)

    password_reset_integration.revoke_unused_tokens(7, db)
    db.commit()

    assert _used(db, "mine") is True
    assert _used(db, "other") is False
