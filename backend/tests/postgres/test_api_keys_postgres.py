"""API keys against real PostgreSQL: the key limit under concurrency, the stale purge and the schema changes."""

import importlib.util
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import psycopg.errors
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.auth.account_security.api_key_service as api_key_service
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.crud as api_keys_crud
import modules.auth.api_keys.models as api_keys_models
import modules.auth.api_keys.schema as api_keys_schema
import modules.users.users.models as users_models
from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.db import ensure_user

_MIGRATION_83 = Path(__file__).resolve().parents[2] / "app/alembic/versions/v0_21_0/83_api_key_revoked_at.py"
_THREADS = 4
_HAS_REVOKED_AT = (
    "SELECT count(*) FROM information_schema.columns WHERE table_name = 'users_api_keys' AND column_name = 'revoked_at'"
)


def _add_key(db, *, active: bool, expires_at: datetime, revoked_at: datetime | None = None, user_id=MOCK_USER_ID):
    key_id = uuid.uuid4()
    db.add(
        api_keys_models.UsersApiKeys(
            id=key_id,
            user_id=user_id,
            name="k",
            key_prefix="abcdefgh",
            key_hash=key_id.hex,
            scopes="[]",
            expires_at=expires_at,
            created_at=datetime.now(UTC) - timedelta(days=400),
            is_active=active,
            revoked_at=revoked_at,
        )
    )
    return key_id


def _data() -> api_keys_schema.UserApiKeyCreate:
    return api_keys_schema.UserApiKeyCreate(name="k", scopes=["activities:upload"], step_up={"current_password": "pw"})


def test_concurrent_creations_cannot_pass_the_key_limit_together(pg_factory):
    ensure_user(pg_factory, MOCK_USER_ID)
    cap = api_keys_constants.MAX_ACTIVE_API_KEYS_PER_USER
    future = datetime.now(UTC) + timedelta(days=30)
    with pg_factory() as db:
        for _ in range(cap - 1):
            _add_key(db, active=True, expires_at=future)
        db.commit()

    barrier = threading.Barrier(_THREADS)
    outcomes: list = []

    def create() -> None:
        barrier.wait()
        with pg_factory() as db:
            try:
                outcomes.append(
                    api_key_service.create_user_api_key(MOCK_USER_ID, uuid.uuid4(), _data(), future, MagicMock(), db)
                )
            except Exception as err:
                db.rollback()
                outcomes.append(err)

    real_count = api_key_service.api_keys_integration.count_active_api_keys

    def slow_count(user_id, db):
        """Count, then linger, so a creation that is not serialised lets the others count the same value."""
        counted = real_count(user_id, db)
        time.sleep(0.3)
        return counted

    with (
        patch.object(api_key_service.api_keys_integration, "count_active_api_keys", side_effect=slow_count),
        patch.object(api_key_service.step_up_service, "verify_step_up_credentials"),
        patch.object(api_key_service.account_security_event_publishers, "publish_account_security_changed"),
        patch.object(api_key_service, "_stage_key_audit"),
    ):
        threads = [threading.Thread(target=create) for _ in range(_THREADS)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)

    created = [o for o in outcomes if isinstance(o, api_keys_schema.UserApiKeyCreatedRead)]
    refused = [o for o in outcomes if isinstance(o, core_exceptions.ApiKeyLimitError)]
    assert len(outcomes) == _THREADS
    assert len(created) == 1, outcomes
    assert len(refused) == _THREADS - 1
    with pg_factory() as db:
        assert api_keys_crud.count_active_api_keys(MOCK_USER_ID, datetime.now(UTC), db) == cap


def test_count_active_api_keys_skips_revoked_and_expired_keys(pg_factory):
    ensure_user(pg_factory, MOCK_USER_ID)
    now = datetime.now(UTC)
    with pg_factory() as db:
        _add_key(db, active=True, expires_at=now + timedelta(days=1))
        _add_key(db, active=True, expires_at=now + timedelta(days=2))
        _add_key(db, active=False, expires_at=now + timedelta(days=2), revoked_at=now)
        _add_key(db, active=True, expires_at=now - timedelta(seconds=1))
        db.commit()

        assert api_keys_crud.count_active_api_keys(MOCK_USER_ID, now, db) == 2


def test_delete_stale_api_keys_removes_only_keys_revoked_or_expired_before_the_cutoff(pg_factory):
    ensure_user(pg_factory, MOCK_USER_ID)
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=30)
    with pg_factory() as db:
        kept = {
            _add_key(db, active=True, expires_at=now + timedelta(days=1)),
            _add_key(db, active=False, expires_at=now + timedelta(days=1), revoked_at=now - timedelta(days=1)),
            _add_key(db, active=True, expires_at=now - timedelta(days=1)),
        }
        _add_key(db, active=False, expires_at=now + timedelta(days=1), revoked_at=cutoff - timedelta(days=1))
        _add_key(db, active=True, expires_at=cutoff - timedelta(days=1))
        db.commit()

        assert api_keys_crud.delete_stale_api_keys(cutoff, 100, db) == 2
        db.commit()
        remaining = set(db.execute(text("SELECT id FROM users_api_keys")).scalars())

    assert remaining == kept


def test_delete_stale_api_keys_honours_the_batch_limit(pg_factory):
    ensure_user(pg_factory, MOCK_USER_ID)
    now = datetime.now(UTC)
    with pg_factory() as db:
        for _ in range(3):
            _add_key(db, active=True, expires_at=now - timedelta(days=60))
        db.commit()

        assert api_keys_crud.delete_stale_api_keys(now - timedelta(days=30), 2, db) == 2


def test_revision_83_backfills_revoked_keys_with_the_upgrade_time(pg_factory):
    ensure_user(pg_factory, MOCK_USER_ID)
    future = datetime.now(UTC) + timedelta(days=30)
    with pg_factory() as db:
        revoked = _add_key(db, active=False, expires_at=future)
        active = _add_key(db, active=True, expires_at=future)
        db.commit()

        spec = importlib.util.spec_from_file_location("api_key_revoked_at", _MIGRATION_83)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        before = db.scalar(text("SELECT now()"))
        with (
            patch.object(migration.op, "add_column"),
            patch.object(migration.op, "execute", side_effect=lambda sql: db.execute(text(sql))),
        ):
            migration.upgrade()
        db.commit()
        rows = dict(db.execute(text("SELECT id, revoked_at FROM users_api_keys")).all())
        created_at = db.scalar(text("SELECT created_at FROM users_api_keys WHERE id = :id"), {"id": revoked})

    assert rows[active] is None
    assert rows[revoked] >= before
    assert rows[revoked] > created_at + timedelta(days=300)


def _user(access_type: str) -> users_models.Users:
    user_id = uuid.uuid4()
    return users_models.Users(
        id=user_id,
        name="S",
        username=f"user{user_id.hex}",
        email=f"{user_id.hex}@example.com",
        preferred_language="en",
        access_type=access_type,
    )


def test_the_users_access_type_check_refuses_an_unknown_access_type(pg_factory):
    with pg_factory() as db:
        db.add(_user("regular"))
        db.commit()

        db.add(_user("superuser"))
        with pytest.raises(IntegrityError) as err:
            db.commit()
        db.rollback()

    assert isinstance(err.value.orig, psycopg.errors.CheckViolation)
    assert err.value.orig.diag.constraint_name == "ck_users_access_type"


def test_revision_83_downgrade_drops_the_revocation_time(pg_factory):
    spec = importlib.util.spec_from_file_location("api_key_revoked_at", _MIGRATION_83)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with pg_factory() as db:
        assert db.scalar(text(_HAS_REVOKED_AT)) == 1
        with patch.object(
            migration.op,
            "drop_column",
            side_effect=lambda table, column: db.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}")),
        ):
            migration.downgrade()
        db.commit()

        assert db.scalar(text(_HAS_REVOKED_AT)) == 0
