"""Tests for the activity thumbnail integration surface."""

from unittest.mock import patch

MODULE = "modules.activities.activity_thumbnail.integration_service"


class TestThumbnailUrl:
    @patch(f"{MODULE}.activity_thumbnail_signing")
    def test_delegates_to_signing(self, mock_signing):
        from modules.activities.activity_thumbnail.integration_service import thumbnail_url

        mock_signing.thumbnail_url.return_value = "/u"

        assert thumbnail_url("k", 7) == "/u"
        mock_signing.thumbnail_url.assert_called_once_with("k", 7)
