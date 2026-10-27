"""Tests for the activity profile-summary integration surface."""

from datetime import date
from unittest.mock import MagicMock, patch

import modules.activities.activity.integration_service as activity_integration


def test_profile_summary_reaches_the_activity_service():
    db = MagicMock()
    with patch.object(activity_integration.activity_service, "user_profile_summary", return_value="summary") as summary:
        result = activity_integration.get_user_profile_summary(7, 3, db, anchor=date(2026, 10, 27))

    assert result == "summary"
    summary.assert_called_once_with(7, 3, db, anchor=date(2026, 10, 27))
