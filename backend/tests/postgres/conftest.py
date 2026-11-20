"""Fixtures for the tests that check behaviour only PostgreSQL shows.

Per-session connection isolation, a failed flush poisoning the session until rollback, row locks and the unique
indexes the application leans on. The databases come from the run's harness (``tests/_helpers/database.py``).
"""

import pytest

from tests._helpers import database as test_database


def pytest_collection_modifyitems(items):
    """Mark every test in this directory so ``-m postgres`` selects them."""
    for item in items:
        if "tests/postgres/" in str(item.fspath).replace("\\", "/"):
            item.add_marker(pytest.mark.postgres)


@pytest.fixture
def pg_factory(committed_sessions):
    """The application's session factory with real commits; the name the tests in this directory use."""
    return committed_sessions


@pytest.fixture
def upgrade_db(_worker_database):
    """Yield an engine on an empty database of this process's own, for the tests that run the real Alembic chain."""
    engine = test_database.create_chain_database()
    try:
        yield engine
    finally:
        engine.dispose()
