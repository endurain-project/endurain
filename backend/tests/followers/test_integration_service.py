"""Tests for the followers module surface."""

import uuid
from unittest.mock import MagicMock, patch

import modules.followers.integration_service as followers_integration

_ID_3 = uuid.uuid4()
_ID_7 = uuid.uuid4()


def test_profile_follow_counts_reach_the_followers_service():
    db = MagicMock()
    with patch.object(
        followers_integration.followers_service,
        "get_profile_follow_counts",
        return_value="counts",
    ) as counts:
        result = followers_integration.get_profile_follow_counts(_ID_7, _ID_3, db)

    assert result == "counts"
    counts.assert_called_once_with(_ID_7, _ID_3, db)
