"""Account security generations, against real PostgreSQL."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

import modules.auth.constants as auth_constants
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.models as sessions_models
from tests._helpers.db import ensure_user


def _row(pg_factory, user_id):
    with pg_factory() as db:
        return db.execute(
            text("SELECT generation FROM account_security_generations WHERE user_id = :u"), {"u": user_id}
        ).scalar_one_or_none()


def test_current_generation_is_zero_without_writing_a_row_and_follows_bumps(pg_factory):
    ensure_user(pg_factory, 1)
    with pg_factory() as db:
        assert security_generation_integration.current_generation(1, db) == 0
        db.commit()
    assert _row(pg_factory, 1) is None
    with pg_factory() as db:
        security_generation_integration.stage_bump(1, db)
        db.commit()
    with pg_factory() as db:
        assert security_generation_integration.current_generation(1, db) == 1


def test_bump_from_a_missing_row_inserts_one(pg_factory):
    ensure_user(pg_factory, 1)
    assert _row(pg_factory, 1) is None
    with pg_factory() as db:
        security_generation_integration.stage_bump(1, db)
        db.commit()
    assert _row(pg_factory, 1) == 1


def test_bump_twice_advances_by_two(pg_factory):
    ensure_user(pg_factory, 1)
    with pg_factory() as db:
        security_generation_integration.stage_bump(1, db)
        security_generation_integration.stage_bump(1, db)
        db.commit()
    assert _row(pg_factory, 1) == 2


def test_matches_locked_accepts_the_current_stamp_and_refuses_after_a_bump(pg_factory):
    ensure_user(pg_factory, 1)
    with pg_factory() as db:
        stamped = security_generation_integration.current_generation(1, db)
    with pg_factory() as db:
        # No row exists yet: the check creates it at 0 so that it can lock it.
        assert security_generation_integration.matches_locked(1, stamped, db) is True
        assert security_generation_integration.matches_locked(1, None, db) is False
        db.commit()
    assert _row(pg_factory, 1) == 0
    with pg_factory() as db:
        security_generation_integration.stage_bump(1, db)
        db.commit()
    with pg_factory() as db:
        assert security_generation_integration.matches_locked(1, stamped, db) is False


def test_a_bump_waits_for_a_redeem_holding_the_lock(pg_factory):
    ensure_user(pg_factory, 1)
    with pg_factory() as redeem, pg_factory() as change:
        assert security_generation_integration.matches_locked(1, 0, redeem) is True
        change.execute(text("SET lock_timeout = '200ms'"))
        with pytest.raises(OperationalError):
            security_generation_integration.stage_bump(1, change)
        change.rollback()
        redeem.commit()
    with pg_factory() as change:
        security_generation_integration.stage_bump(1, change)
        change.commit()
    assert _row(pg_factory, 1) == 1


def test_the_row_goes_with_its_user(pg_factory):
    ensure_user(pg_factory, 1)
    with pg_factory() as db:
        security_generation_integration.stage_bump(1, db)
        db.commit()
    with pg_factory() as db:
        db.execute(text("DELETE FROM users WHERE id = 1"))
        db.commit()
    assert _row(pg_factory, 1) is None


def _add_session(db, session_id, user_id=1):
    now = datetime.now(UTC)
    db.add(
        sessions_models.UsersSessions(
            id=session_id,
            user_id=user_id,
            ip_address="127.0.0.1",
            device_type="desktop",
            operating_system="linux",
            operating_system_version="1",
            browser="firefox",
            browser_version="1",
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(days=1),
            token_family_id=f"family-{session_id}",
            client_type=auth_constants.ClientType.WEB,
            auth_time=now,
            amr=["pwd"],
        )
    )
    db.flush()


def _session_ids(pg_factory):
    with pg_factory() as db:
        return set(db.execute(text("SELECT id FROM users_sessions")).scalars())


def test_a_redeem_waits_on_an_uncommitted_bump_and_then_sees_the_new_generation(pg_factory):
    ensure_user(pg_factory, 1)
    with pg_factory() as change, pg_factory() as redeem:
        security_generation_integration.stage_bump(1, change)
        redeem.execute(text("SET lock_timeout = '200ms'"))
        with pytest.raises(OperationalError):
            security_generation_integration.matches_locked(1, 0, redeem)
        redeem.rollback()
        change.commit()
    with pg_factory() as redeem:
        assert security_generation_integration.matches_locked(1, 0, redeem) is False
        assert security_generation_integration.matches_locked(1, 1, redeem) is True


def test_a_bump_then_delete_leaves_no_session_a_concurrent_redeem_could_add(pg_factory):
    ensure_user(pg_factory, 1)
    with pg_factory() as db:
        _add_session(db, "old")
        db.commit()

    # The change takes the generation lock first and ends the sessions; the redeem waits and is then refused.
    with pg_factory() as change, pg_factory() as redeem:
        security_generation_integration.stage_bump(1, change)
        change.execute(text("DELETE FROM users_sessions WHERE user_id = 1"))
        redeem.execute(text("SET lock_timeout = '200ms'"))
        with pytest.raises(OperationalError):
            security_generation_integration.matches_locked(1, 0, redeem)
        redeem.rollback()
        change.commit()
    with pg_factory() as redeem:
        assert security_generation_integration.matches_locked(1, 0, redeem) is False
        redeem.rollback()
    assert _session_ids(pg_factory) == set()

    # A redeem that holds the lock first adds its session before the change can bump; the change then ends it too.
    with pg_factory() as redeem, pg_factory() as change:
        generation = security_generation_integration.current_generation(1, redeem)
        assert security_generation_integration.matches_locked(1, generation, redeem) is True
        _add_session(redeem, "new")
        change.execute(text("SET lock_timeout = '200ms'"))
        with pytest.raises(OperationalError):
            security_generation_integration.stage_bump(1, change)
        change.rollback()
        redeem.commit()
    with pg_factory() as change:
        security_generation_integration.stage_bump(1, change)
        change.execute(text("DELETE FROM users_sessions WHERE user_id = 1"))
        change.commit()
    assert _session_ids(pg_factory) == set()


def test_a_locked_live_session_cannot_be_revoked_until_the_transaction_ends(pg_factory):
    import modules.auth.sessions.integration_service as sessions_integration

    ensure_user(pg_factory, 1)
    with pg_factory() as db:
        _add_session(db, "start")
        db.commit()

    with pg_factory() as link, pg_factory() as revoke:
        assert sessions_integration.lock_live_session("start", link) is not None
        revoke.execute(text("SET lock_timeout = '200ms'"))
        with pytest.raises(OperationalError):
            revoke.execute(text("DELETE FROM users_sessions WHERE id = 'start'"))
        revoke.rollback()
        link.commit()
    with pg_factory() as revoke:
        revoke.execute(text("DELETE FROM users_sessions WHERE id = 'start'"))
        revoke.commit()
    with pg_factory() as db:
        assert sessions_integration.lock_live_session("start", db) is None
