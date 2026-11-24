"""Fixtures of the activity detail tests."""

from collections.abc import Callable
from typing import Any

import pytest


@pytest.fixture
def arrange(committed_sessions) -> Callable[[Callable[[Any], Any]], Any]:
    """Return a function that runs an arranging step in a session it commits, and returns the step's result."""

    def run(step: Callable[[Any], Any]) -> Any:
        with committed_sessions() as db:
            result = step(db)
            db.commit()
        return result

    return run
