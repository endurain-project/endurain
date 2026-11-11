"""Fixtures shared by the users service tests."""

from unittest.mock import patch

import pytest

_SERVICE = "modules.users.users.service"


@pytest.fixture
def real_email_availability():
    """Request the real address check, which the tests below this fixture's users leave out."""


@pytest.fixture(autouse=True)
def email_availability(request):
    """Leave every address available, since these tests run against a mocked database session.

    A test that exercises the check itself requests ``real_email_availability``; the reservation lookup, which
    needs a real session, still answers that no address is reserved.
    """
    if "real_email_availability" in request.fixturenames:
        with patch(f"{_SERVICE}.sign_up_tokens_integration.get_email_reserver_id", return_value=None):
            yield
    else:
        with patch(f"{_SERVICE}.is_email_available", return_value=True):
            yield
