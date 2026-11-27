"""Tests for the activity thumbnail integration surface."""

import uuid
from unittest.mock import patch

ACTIVITY_ID = uuid.UUID("00000000-0000-4000-8000-000000000042")
OTHER_ID = uuid.UUID("00000000-0000-4000-8000-000000000043")

MODULE = "modules.activities.activity_thumbnail.integration_service"


class TestThumbnailUrl:
    @patch(f"{MODULE}.activity_thumbnail_signing")
    def test_delegates_to_signing(self, mock_signing):
        from modules.activities.activity_thumbnail.integration_service import thumbnail_url

        mock_signing.thumbnail_url.return_value = "/u"

        assert thumbnail_url("k", ACTIVITY_ID) == "/u"
        mock_signing.thumbnail_url.assert_called_once_with("k", ACTIVITY_ID)
