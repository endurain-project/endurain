"""The interval of a list request is resolved against the user's own calendar."""

from datetime import date
from unittest.mock import MagicMock, patch

import modules.health.constants as health_constants
import modules.health.interval_service as interval_service


def test_no_interval_means_no_lower_bound():
    assert interval_service.interval_start(1, None, MagicMock()) is None


def test_an_interval_starts_before_the_users_own_today():
    interval = next(iter(health_constants.Interval))

    with patch.object(interval_service.users_integration, "local_today", return_value=date(2026, 3, 15)) as today:
        start = interval_service.interval_start(7, interval, MagicMock())

    today.assert_called_once()
    assert start is not None
    assert start <= date(2026, 3, 15)
