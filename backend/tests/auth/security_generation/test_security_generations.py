"""Account security generations: the counter, its row lock and what it fences, against real PostgreSQL."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

import core.exceptions as core_exceptions
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.service as authentication_service
import modules.auth.constants as auth_constants
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.models as sessions_models
from tests._factories.users import make_user


def _new_user(committed_sessions) -> uuid.UUID:
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    return user.id


def _row(committed_sessions, user_id):
    with committed_sessions() as db:
        return db.execute(
            text("SELECT generation FROM account_security_generations WHERE user_id = :u"), {"u": user_id}
        ).scalar_one_or_none()


def test_current_generation_is_zero_without_writing_a_row_and_follows_bumps(committed_sessions):
    user_id = _new_user(committed_sessions)
    with committed_sessions() as db:
        assert security_generation_integration.current_generation(user_id, db) == 0
        db.commit()
    assert _row(committed_sessions, user_id) is None
    with committed_sessions() as db:
        security_generation_integration.stage_bump(user_id, db)
        db.commit()
    with committed_sessions() as db:
        assert security_generation_integration.current_generation(user_id, db) == 1


def test_bump_from_a_missing_row_inserts_one(committed_sessions):
    user_id = _new_user(committed_sessions)
    assert _row(committed_sessions, user_id) is None
    with committed_sessions() as db:
        security_generation_integration.stage_bump(user_id, db)
        db.commit()
    assert _row(committed_sessions, user_id) == 1


def test_bump_twice_advances_by_two(committed_sessions):
    user_id = _new_user(committed_sessions)
    with committed_sessions() as db:
        security_generation_integration.stage_bump(user_id, db)
        security_generation_integration.stage_bump(user_id, db)
        db.commit()
    assert _row(committed_sessions, user_id) == 2


def test_matches_locked_accepts_the_current_stamp_and_refuses_after_a_bump(committed_sessions):
    user_id = _new_user(committed_sessions)
    with committed_sessions() as db:
        stamped = security_generation_integration.current_generation(user_id, db)
    with committed_sessions() as db:
        # No row exists yet: the check creates it at 0 so that it can lock it.
        assert security_generation_integration.matches_locked(user_id, stamped, db) is True
        assert security_generation_integration.matches_locked(user_id, None, db) is False
        db.commit()
    assert _row(committed_sessions, user_id) == 0
    with committed_sessions() as db:
        security_generation_integration.stage_bump(user_id, db)
        db.commit()
    with committed_sessions() as db:
        assert security_generation_integration.matches_locked(user_id, stamped, db) is False


def test_a_bump_waits_for_a_redeem_holding_the_lock(committed_sessions):
    user_id = _new_user(committed_sessions)
    with committed_sessions() as redeem, committed_sessions() as change:
        assert security_generation_integration.matches_locked(user_id, 0, redeem) is True
        change.execute(text("SET lock_timeout = '200ms'"))
        with pytest.raises(OperationalError):
            security_generation_integration.stage_bump(user_id, change)
        change.rollback()
        redeem.commit()
    with committed_sessions() as change:
        security_generation_integration.stage_bump(user_id, change)
        change.commit()
    assert _row(committed_sessions, user_id) == 1


def test_lock_creates_the_row_at_zero_and_holds_it_against_a_bump_until_the_transaction_ends(committed_sessions):
    user_id = _new_user(committed_sessions)
    with committed_sessions() as locker, committed_sessions() as change:
        security_generation_integration.lock(user_id, locker)
        change.execute(text("SET lock_timeout = '200ms'"))
        with pytest.raises(OperationalError):
            security_generation_integration.stage_bump(user_id, change)
        change.rollback()
        locker.commit()
    assert _row(committed_sessions, user_id) == 0
    with committed_sessions() as change:
        security_generation_integration.stage_bump(user_id, change)
        change.commit()
    assert _row(committed_sessions, user_id) == 1


def test_the_row_goes_with_its_user(committed_sessions):
    user_id = _new_user(committed_sessions)
    with committed_sessions() as db:
        security_generation_integration.stage_bump(user_id, db)
        db.commit()
    with committed_sessions() as db:
        db.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
        db.commit()
    assert _row(committed_sessions, user_id) is None


def _add_session(db, session_id, user_id):
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
            token_family_id=session_id,
            client_type=auth_constants.ClientType.WEB,
            auth_time=now,
            amr=["pwd"],
        )
    )
    db.flush()


_OLD_SESSION, _NEW_SESSION, _START_SESSION, _S1_SESSION = (uuid.uuid4() for _ in range(4))


def _session_ids(committed_sessions):
    with committed_sessions() as db:
        return set(db.execute(text("SELECT id FROM users_sessions")).scalars())


def test_a_redeem_waits_on_an_uncommitted_bump_and_then_sees_the_new_generation(committed_sessions):
    user_id = _new_user(committed_sessions)
    with committed_sessions() as change, committed_sessions() as redeem:
        security_generation_integration.stage_bump(user_id, change)
        redeem.execute(text("SET lock_timeout = '200ms'"))
        with pytest.raises(OperationalError):
            security_generation_integration.matches_locked(user_id, 0, redeem)
        redeem.rollback()
        change.commit()
    with committed_sessions() as redeem:
        assert security_generation_integration.matches_locked(user_id, 0, redeem) is False
        assert security_generation_integration.matches_locked(user_id, 1, redeem) is True


def test_a_bump_then_delete_leaves_no_session_a_concurrent_redeem_could_add(committed_sessions):
    user_id = _new_user(committed_sessions)
    with committed_sessions() as db:
        _add_session(db, _OLD_SESSION, user_id)
        db.commit()

    # The change takes the generation lock first and ends the sessions; the redeem waits and is then refused.
    with committed_sessions() as change, committed_sessions() as redeem:
        security_generation_integration.stage_bump(user_id, change)
        change.execute(text("DELETE FROM users_sessions WHERE user_id = :u"), {"u": user_id})
        redeem.execute(text("SET lock_timeout = '200ms'"))
        with pytest.raises(OperationalError):
            security_generation_integration.matches_locked(user_id, 0, redeem)
        redeem.rollback()
        change.commit()
    with committed_sessions() as redeem:
        assert security_generation_integration.matches_locked(user_id, 0, redeem) is False
        redeem.rollback()
    assert _session_ids(committed_sessions) == set()

    # A redeem that holds the lock first adds its session before the change can bump; the change then ends it too.
    with committed_sessions() as redeem, committed_sessions() as change:
        generation = security_generation_integration.current_generation(user_id, redeem)
        assert security_generation_integration.matches_locked(user_id, generation, redeem) is True
        _add_session(redeem, _NEW_SESSION, user_id)
        change.execute(text("SET lock_timeout = '200ms'"))
        with pytest.raises(OperationalError):
            security_generation_integration.stage_bump(user_id, change)
        change.rollback()
        redeem.commit()
    with committed_sessions() as change:
        security_generation_integration.stage_bump(user_id, change)
        change.execute(text("DELETE FROM users_sessions WHERE user_id = :u"), {"u": user_id})
        change.commit()
    assert _session_ids(committed_sessions) == set()


def test_a_locked_live_session_cannot_be_revoked_until_the_transaction_ends(committed_sessions):
    import modules.auth.sessions.integration_service as sessions_integration

    user_id = _new_user(committed_sessions)
    with committed_sessions() as db:
        _add_session(db, _START_SESSION, user_id)
        db.commit()

    with committed_sessions() as link, committed_sessions() as revoke:
        assert sessions_integration.lock_live_session(_START_SESSION, link) is not None
        revoke.execute(text("SET lock_timeout = '200ms'"))
        with pytest.raises(OperationalError):
            revoke.execute(text("DELETE FROM users_sessions WHERE id = :i"), {"i": _START_SESSION})
        revoke.rollback()
        link.commit()
    with committed_sessions() as revoke:
        revoke.execute(text("DELETE FROM users_sessions WHERE id = :i"), {"i": _START_SESSION})
        revoke.commit()
    with committed_sessions() as db:
        assert sessions_integration.lock_live_session(_START_SESSION, db) is None


def test_a_revoke_waits_for_a_refresh_holding_the_session_and_a_refresh_after_it_finds_none(committed_sessions):
    import modules.auth.sessions.integration_service as sessions_integration

    user_id = _new_user(committed_sessions)
    with committed_sessions() as db:
        _add_session(db, _S1_SESSION, user_id)
        db.commit()
    with committed_sessions() as refresh, committed_sessions() as revoke:
        assert sessions_integration.lock_live_session(_S1_SESSION, refresh, exclusive=True) is not None
        revoke.execute(text("SET lock_timeout = '200ms'"))
        with pytest.raises(OperationalError):
            sessions_integration.delete_session_if_present(_S1_SESSION, user_id, revoke)
        revoke.rollback()
        refresh.commit()
    with committed_sessions() as revoke:
        sessions_integration.delete_session_if_present(_S1_SESSION, user_id, revoke)
        revoke.commit()
    with committed_sessions() as refresh:
        assert sessions_integration.lock_live_session(_S1_SESSION, refresh, exclusive=True) is None


def _web_sign_in(db, user, stamp):
    return authentication_service.complete_login(
        "127.0.0.1",
        "agent",
        user,
        access_tokens_integration.get_token_manager(),
        db,
        mfa=False,
        security_generation=stamp,
        device_hash=None,
    )


def test_a_web_sign_in_whose_generation_was_read_before_a_committed_bump_creates_no_session(committed_sessions):
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    with committed_sessions() as login:
        # The sign-in reads the generation, then verifies the password.
        stamp = security_generation_integration.current_generation(user.id, login)
        login.rollback()

        # A reset commits while the hash runs: the generation advances and the account's sessions end.
        with committed_sessions() as change:
            security_generation_integration.stage_bump(user.id, change)
            change.execute(text("DELETE FROM users_sessions WHERE user_id = :u"), {"u": user.id})
            change.commit()

        with pytest.raises(core_exceptions.UnauthenticatedError):
            _web_sign_in(login, user, stamp)
        login.rollback()

    assert _session_ids(committed_sessions) == set()


def test_a_web_sign_in_with_the_current_generation_creates_its_session(committed_sessions):
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    with committed_sessions() as login:
        stamp = security_generation_integration.current_generation(user.id, login)
        login.rollback()
        _web_sign_in(login, user, stamp)

    assert len(_session_ids(committed_sessions)) == 1
