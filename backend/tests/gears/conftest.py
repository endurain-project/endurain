from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

import modules.gears.contributor_registry as gears_contributor_registry
from tests._helpers.db import create_sqlite_session


@pytest.fixture
def db():
    session: Session = create_sqlite_session()
    yield session
    session.close()


@pytest.fixture
def commit_spy(db) -> MagicMock:
    """Wrap the session's ``commit`` so a test can assert who ended the transaction."""
    spy = MagicMock(wraps=db.commit)
    db.commit = spy
    return spy


@pytest.fixture(autouse=True)
def _clean_gears_registry():
    gears_contributor_registry.clear()
    yield
    gears_contributor_registry.clear()
