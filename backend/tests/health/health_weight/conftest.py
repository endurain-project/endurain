"""Setup of the weight tests."""

import pytest


@pytest.fixture(autouse=True)
def athletes_clock():
    """Run on the real clock and the user's real timezone, as these tests use real users and the real database.

    ``tests/health/conftest.py`` fixes the athlete's today far ahead for the tests that mock their collaborators; here
    the day a user is on comes from the code under test, so a future date is one after the real today.
    """
    yield
