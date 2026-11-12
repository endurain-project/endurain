"""Tests for staged rotated-token persistence."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.rotated_refresh_tokens.crud as rotated_token_crud
import modules.auth.rotated_refresh_tokens.models as rotated_token_models
import modules.auth.rotated_refresh_tokens.schema as rotated_token_schema
from tests._helpers.db import create_sqlite_session


def _token(**overrides):
    values = {
        "id": 3,
        "token_family_id": "f" * 36,
        "hashed_token": "a" * 64,
        "client_fingerprint": "c" * 64,
        "rotation_count": 1,
        "rotated_at": datetime.now(UTC),
        "expires_at": datetime.now(UTC) + timedelta(seconds=30),
        "replacement_refresh_token": "encrypted",
        "replacement_refresh_token_exp": datetime.now(UTC) + timedelta(days=1),
        "refresh_token_exp": datetime.now(UTC) + timedelta(days=1),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_get_rotated_token_returns_read_schema(mock_db):
    token = _token()
    mock_db.execute.return_value.scalar_one_or_none.return_value = token
    assert rotated_token_crud.get_rotated_token_by_hashes([token.hashed_token], mock_db) == (
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
    assert rotated_token_crud.delete_expired_tokens(datetime.now(UTC), 100, mock_db) == 2
    assert rotated_token_crud.delete_by_family("f" * 36, mock_db) == 2
    assert mock_db.flush.call_count == 2
    mock_db.commit.assert_not_called()


def _stage(db, hashed_token, *, rotated_at, refresh_token_exp):
    values = _token(hashed_token=hashed_token, rotated_at=rotated_at, refresh_token_exp=refresh_token_exp).__dict__
    values.pop("id")
    rotated_token_crud.create_rotated_token(rotated_token_schema.RotatedRefreshTokenCreate(**values), db)


def test_a_record_is_kept_until_its_refresh_token_expires():
    """Reuse detection needs the record for as long as the old token could still be presented.

    A token issued under a 30-day lifetime and rotated 8 days ago is still valid, so its record stays;
    one whose own expiry has passed goes, however recently it was rotated.
    """
    db = create_sqlite_session()
    now = datetime.now(UTC)
    _stage(db, "a" * 64, rotated_at=now - timedelta(days=8), refresh_token_exp=now + timedelta(days=22))
    _stage(db, "b" * 64, rotated_at=now - timedelta(minutes=5), refresh_token_exp=now - timedelta(minutes=1))

    assert rotated_token_crud.delete_expired_tokens(now, 100, db) == 1
    assert rotated_token_crud.get_rotated_token_by_hashes(["a" * 64], db) is not None
    assert rotated_token_crud.get_rotated_token_by_hashes(["b" * 64], db) is None

    db.close()


def test_a_record_is_found_by_any_of_the_digests():
    db = create_sqlite_session()
    now = datetime.now(UTC)
    _stage(db, "a" * 64, rotated_at=now, refresh_token_exp=now + timedelta(days=1))

    assert rotated_token_crud.get_rotated_token_by_hashes(["z" * 64, "a" * 64], db) is not None
    assert rotated_token_crud.get_rotated_token_by_hashes(["y" * 64, "z" * 64], db) is None

    db.close()


def test_a_replacement_is_cleared_once_the_grace_window_has_passed_and_the_record_is_kept():
    """The replacement is needed only inside the grace window; the hash stays for reuse detection."""
    db = create_sqlite_session()
    now = datetime.now(UTC)
    _stage(db, "a" * 64, rotated_at=now - timedelta(minutes=1), refresh_token_exp=now + timedelta(days=1))
    _stage(db, "b" * 64, rotated_at=now, refresh_token_exp=now + timedelta(days=1))
    for digest, expires_at in (("a" * 64, now - timedelta(seconds=1)), ("b" * 64, now + timedelta(seconds=5))):
        row = db.query(rotated_token_models.RotatedRefreshToken).filter_by(hashed_token=digest).one()
        row.expires_at = expires_at
    db.flush()

    assert rotated_token_crud.clear_expired_replacements(now, 100, db) == 1
    assert rotated_token_crud.clear_expired_replacements(now, 100, db) == 0

    expired = rotated_token_crud.get_rotated_token_by_hashes(["a" * 64], db)
    assert expired is not None
    assert expired.replacement_refresh_token is None
    assert expired.replacement_refresh_token_exp is None
    live = rotated_token_crud.get_rotated_token_by_hashes(["b" * 64], db)
    assert live is not None
    assert live.replacement_refresh_token == "encrypted"

    db.close()


def test_clearing_replacements_is_bounded_by_the_limit():
    db = create_sqlite_session()
    now = datetime.now(UTC)
    for digest in ("a" * 64, "b" * 64, "c" * 64):
        _stage(db, digest, rotated_at=now - timedelta(minutes=1), refresh_token_exp=now + timedelta(days=1))
    db.query(rotated_token_models.RotatedRefreshToken).update({"expires_at": now - timedelta(seconds=1)})
    db.flush()

    assert rotated_token_crud.clear_expired_replacements(now, 2, db) == 2
    assert rotated_token_crud.clear_expired_replacements(now, 2, db) == 1

    db.close()


def test_reencryption_skips_a_cleared_replacement():
    db = create_sqlite_session()
    now = datetime.now(UTC)
    _stage(db, "a" * 64, rotated_at=now - timedelta(minutes=1), refresh_token_exp=now + timedelta(days=1))
    db.query(rotated_token_models.RotatedRefreshToken).update({"expires_at": now - timedelta(seconds=1)})
    rotated_token_crud.clear_expired_replacements(now, 100, db)

    result = rotated_token_crud.stage_reencrypt_batch_tokens(None, 100, db)

    assert result.counts.rotated == 0
    assert result.counts.undecryptable == 0

    db.close()
