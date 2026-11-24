"""Fixtures for the migration tests."""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine

from tests._helpers import database as test_database


@pytest.fixture
def upgrade_db(_worker_database) -> Iterator[Engine]:
    """Yield an engine on an empty database of this process's own, for the tests that run the real Alembic chain."""
    engine = test_database.create_chain_database()
    try:
        yield engine
    finally:
        engine.dispose()
