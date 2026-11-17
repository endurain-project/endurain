"""Fixtures shared by the users service tests."""

from unittest.mock import patch

import pytest

_SERVICE = "modules.users.users.service"


@pytest.fixture
def email_available():
    """Leave every address available for a test that runs against a mocked database session and does not test it."""
    with patch(f"{_SERVICE}.is_email_available", return_value=True):
        yield


@pytest.fixture
def real_email_availability():
    """Run the real address check; only the reservation lookup, which needs a real session, finds no reservation."""
    with patch(f"{_SERVICE}.sign_up_tokens_integration.get_email_reserver_id", return_value=None):
        yield
