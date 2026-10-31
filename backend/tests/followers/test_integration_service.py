"""Tests for the followers module surface."""

from unittest.mock import MagicMock, patch

import modules.followers.integration_service as followers_integration


def test_profile_follow_counts_reach_the_followers_service():
    db = MagicMock()
    with patch.object(
        followers_integration.followers_service,
        "get_profile_follow_counts",
        return_value="counts",
    ) as counts:
        result = followers_integration.get_profile_follow_counts(7, 3, db)

    assert result == "counts"
    counts.assert_called_once_with(7, 3, db)
