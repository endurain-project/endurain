"""The generations' own tests exercise the real integration service, not the in-memory stand-in."""

import pytest


@pytest.fixture(autouse=True)
def security_generations() -> None:
    """Keep the real security-generation functions in place."""
