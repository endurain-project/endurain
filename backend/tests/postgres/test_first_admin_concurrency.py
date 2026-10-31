"""Concurrent first-administrator creation against real PostgreSQL.

The users table is empty when onboarding starts, so there is no row to lock. The advisory transaction lock is
what makes two simultaneous requests produce one administrator, and only separate connections can show it.
"""

import threading
import time
from collections.abc import Callable

import pytest
from jasil.backends.state_memory import MemoryState
from sqlalchemy import select

import core.exceptions as core_exceptions
import modules.auth.onboarding.schema as onboarding_schema
import modules.auth.onboarding.service as onboarding_service
import modules.auth.onboarding.token_store as onboarding_token_store
import modules.server_settings.models as server_settings_models
import modules.users.users.crud as users_crud
import modules.users.users.models as users_models
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service

_THREADS = 4


@pytest.fixture(autouse=True)
def _server_settings(pg_factory):
    """The migrations create the settings row; the test schema does not."""
    with pg_factory() as db:
        db.add(server_settings_models.ServerSettings(id=1))
        db.commit()


def _admin(index: int) -> users_schema.FirstAdminCreate:
    return users_schema.FirstAdminCreate(
        name=f"Owner {index}",
        username=f"owner{index}",
        email=f"owner{index}@example.com",
        password="SecurePass1!",
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


def _stage_and_commit(index: int, db) -> int:
    created = users_service.stage_first_admin(_admin(index), db)
    db.commit()
    return created.id


def test_concurrent_first_admin_creation_produces_exactly_one_administrator(pg_factory):
    outcomes = _race(pg_factory, _stage_and_commit)

    created = [o for o in outcomes if isinstance(o, int)]
    conflicts = [o for o in outcomes if isinstance(o, core_exceptions.ConflictError)]
    assert len(outcomes) == _THREADS
    assert len(created) == 1, outcomes
    assert len(conflicts) == _THREADS - 1
    assert _users(pg_factory) == [("admin", True, True)]


def test_the_lock_makes_the_second_caller_wait_until_the_first_transaction_ends(pg_factory):
    with pg_factory() as first:
        users_crud.lock_first_admin_creation(first)
        waiting = threading.Event()
        acquired = threading.Event()

        def second_caller() -> None:
            with pg_factory() as second:
                waiting.set()
                users_crud.lock_first_admin_creation(second)
                acquired.set()

        thread = threading.Thread(target=second_caller)
        thread.start()
        waiting.wait(timeout=10)
        time.sleep(0.5)
        assert not acquired.is_set(), "the second caller must block while the first transaction is open"

        first.rollback()
        thread.join(timeout=10)

    assert acquired.is_set()


def test_the_check_sees_the_user_a_committed_transaction_created(pg_factory):
    with pg_factory() as db:
        assert users_crud.any_user_exists(db) is False
        users_service.stage_first_admin(_admin(0), db)
        db.commit()

    with pg_factory() as db:
        assert users_crud.any_user_exists(db) is True
        with pytest.raises(core_exceptions.ConflictError):
            users_service.stage_first_admin(_admin(1), db)
        db.rollback()

    assert len(_users(pg_factory)) == 1


def test_a_rolled_back_attempt_leaves_the_installation_open_for_the_next_one(pg_factory):
    with pg_factory() as db:
        with pytest.raises(core_exceptions.InvalidInputError):
            users_service.stage_first_admin(
                users_schema.FirstAdminCreate(name="O", username="o", email="o@example.com", password="short123"), db
            )
        db.rollback()

    with pg_factory() as db:
        assert users_crud.any_user_exists(db) is False
        users_service.stage_first_admin(_admin(0), db)
        db.commit()

    assert len(_users(pg_factory)) == 1


def test_two_onboardings_with_two_valid_tokens_create_one_administrator(pg_factory):
    state = MemoryState()
    store = onboarding_token_store.OnboardingTokenStore(state)
    tokens = [store.issue() for _ in range(_THREADS)]

    def complete(index: int, db):
        request = onboarding_schema.OnboardingCreate(token=tokens[index], **_admin(index).model_dump())
        return onboarding_service.complete_onboarding(request, store, db).id

    outcomes = _race(pg_factory, complete)

    created = [o for o in outcomes if isinstance(o, int)]
    refused = [o for o in outcomes if isinstance(o, core_exceptions.ConflictError)]
    assert len(created) == 1, outcomes
    assert len(refused) == _THREADS - 1
    assert _users(pg_factory) == [("admin", True, True)]
    assert sum(store.exists(token) for token in tokens) == _THREADS - 1, "only the winner's token is consumed"
