"""Concurrent first-administrator creation against real PostgreSQL.

The users table is empty when onboarding starts, so there is no row to lock. The advisory transaction lock is
what makes two simultaneous requests produce one administrator, and only separate connections can show it.
"""

import threading
import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import select, text

import core.database as core_database
import core.exceptions as core_exceptions
import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.onboarding.schema as onboarding_schema
import modules.auth.onboarding.service as onboarding_service
import modules.auth.onboarding.token_store as onboarding_token_store
import modules.users.users.crud as users_crud
import modules.users.users.models as users_models
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service
from tests._helpers.clock import memory_state

_THREADS = 4


def _admin(index: int) -> users_schema.FirstAdminCreate:
    return users_schema.FirstAdminCreate(
        name=f"Owner {index}",
        username=f"owner{index}",
        email=f"owner{index}@example.com",
        password="a secure owner passphrase",
    )


def _race(factory, work: Callable, count: int = _THREADS) -> list:
    """Run ``work(index, db)`` on ``count`` sessions released together; return each outcome."""
    barrier = threading.Barrier(count)
    outcomes: list = []

    def run(index: int) -> None:
        barrier.wait()
        with factory() as db:
            try:
                outcomes.append(work(index, db))
            except Exception as err:
                db.rollback()
                outcomes.append(err)

    threads = [threading.Thread(target=run, args=(index,)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    return outcomes


def _users(factory) -> list[tuple[str, bool, bool]]:
    with factory() as db:
        rows = db.execute(
            select(users_models.Users.access_type, users_models.Users.active, users_models.Users.email_verified)
        ).all()
    return [tuple(row) for row in rows]


def _stage_and_commit(index: int, db) -> uuid.UUID:
    created = users_service.stage_first_admin(_admin(index), db)
    db.commit()
    return created.id


def test_concurrent_first_admin_creation_produces_exactly_one_administrator(committed_sessions):
    outcomes = _race(committed_sessions, _stage_and_commit)

    created = [o for o in outcomes if isinstance(o, uuid.UUID)]
    conflicts = [o for o in outcomes if isinstance(o, core_exceptions.ConflictError)]
    assert len(outcomes) == _THREADS
    assert len(created) == 1, outcomes
    assert len(conflicts) == _THREADS - 1
    assert _users(committed_sessions) == [("admin", True, True)]


def _sessions_waiting_for_an_advisory_lock() -> int:
    """Count the sessions blocked on an advisory lock, read outside any transaction so each poll sees a fresh state."""
    with core_database.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        return connection.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND wait_event_type = 'Lock' AND wait_event = 'advisory'"
            )
        ).scalar_one()


def test_the_lock_makes_the_second_caller_wait_until_the_first_transaction_ends(committed_sessions):
    with committed_sessions() as first:
        users_crud.lock_first_admin_creation(first)
        acquired = threading.Event()

        def second_caller() -> None:
            with committed_sessions() as second:
                users_crud.lock_first_admin_creation(second)
                acquired.set()

        thread = threading.Thread(target=second_caller)
        thread.start()
        blocked = threading.Event()
        for _ in range(200):
            if _sessions_waiting_for_an_advisory_lock() == 1:
                blocked.set()
                break
            acquired.wait(timeout=0.05)
        assert blocked.is_set(), "the second caller must block while the first transaction is open"
        assert not acquired.is_set()

        first.rollback()
        thread.join(timeout=10)

    assert acquired.is_set()


def test_the_check_sees_the_user_a_committed_transaction_created(committed_sessions):
    with committed_sessions() as db:
        assert users_crud.any_user_exists(db) is False
        users_service.stage_first_admin(_admin(0), db)
        db.commit()

    with committed_sessions() as db:
        assert users_crud.any_user_exists(db) is True
        with pytest.raises(core_exceptions.ConflictError):
            users_service.stage_first_admin(_admin(1), db)
        db.rollback()

    assert len(_users(committed_sessions)) == 1


def test_a_rolled_back_attempt_leaves_the_installation_open_for_the_next_one(committed_sessions):
    with committed_sessions() as db:
        with pytest.raises(credentials_contracts.PasswordTooShortError):
            users_service.stage_first_admin(
                users_schema.FirstAdminCreate(name="O", username="o", email="o@example.com", password="short123"), db
            )
        db.rollback()

    with committed_sessions() as db:
        assert users_crud.any_user_exists(db) is False
        users_service.stage_first_admin(_admin(0), db)
        db.commit()

    assert len(_users(committed_sessions)) == 1


def test_two_onboardings_with_two_valid_tokens_create_one_administrator(committed_sessions):
    state = memory_state()
    store = onboarding_token_store.OnboardingTokenStore(state)
    tokens = [store.issue() for _ in range(_THREADS)]

    def complete(index: int, db):
        request = onboarding_schema.OnboardingCreate(token=tokens[index], **_admin(index).model_dump())
        return onboarding_service.complete_onboarding(request, store, db).id

    outcomes = _race(committed_sessions, complete)

    created = [o for o in outcomes if isinstance(o, uuid.UUID)]
    refused = [o for o in outcomes if isinstance(o, core_exceptions.ConflictError)]
    assert len(created) == 1, outcomes
    assert len(refused) == _THREADS - 1
    assert _users(committed_sessions) == [("admin", True, True)]
    assert sum(store.exists(token) for token in tokens) == _THREADS - 1, "only the winner's token is consumed"
