import pytest
from sqlalchemy.orm import Session

import modules.gears.contributor_registry as gears_contributor_registry
from tests._helpers.db import create_sqlite_session


@pytest.fixture
def db():
    session: Session = create_sqlite_session()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def _clean_gears_registry():
    gears_contributor_registry.clear()
    yield
    gears_contributor_registry.clear()
