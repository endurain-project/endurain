"""Shared fixtures for the health tests.

Health queries now resolve "today" and the day-bucketing zone from the athlete's
``users.timezone`` rather than the server clock, which means most CRUD calls hit
the database for the owning user. These tests drive those functions with a mock
session, so the lookup is stubbed centrally here instead of being patched in
every test module.
"""

from datetime import date
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def stub_user_timezone():
    """Pin the athlete's timezone and "today" so health tests stay deterministic.

    Patched on ``modules.users.users.utils`` itself: every health module calls
    these through the module attribute (``users_utils.user_local_today(...)``),
    so one patch covers them all.
    """
    with (
        patch("modules.users.users.utils.resolve_user_timezone", return_value="UTC") as tz,
        patch("modules.users.users.utils.user_local_today", return_value=date(2024, 1, 15)) as today,
    ):
        yield tz, today
