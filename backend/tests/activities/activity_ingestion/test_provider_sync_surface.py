"""The provider-facing surface of activity ingestion."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import modules.activities.activity_ingestion.integration_service as ingestion_integration
import modules.activities.activity_ingestion.provider_registry as provider_registry


class TestRequestProviderSync:
    def test_accepts_a_refresh_scoped_to_the_provider_and_window(self):
        start = datetime(2026, 1, 1, tzinfo=UTC)
        end = datetime(2026, 1, 8, tzinfo=UTC)
        db = MagicMock()
        with patch.object(ingestion_integration.activity_ingestion_service, "accept_refresh") as accept:
            result = ingestion_integration.request_provider_sync(7, "strava", start, end, "storage", db)

        accept.assert_called_once_with(7, "storage", db, provider="strava", window_start=start, window_end=end)
        assert result is accept.return_value


class TestRegisterActivityProvider:
    def test_the_registration_carries_both_the_fetch_and_the_linked_user_pager(self):
        provider_registry.clear()
        try:

            def fetch(user_id, start, end):
                return None

            def linked(after_id, limit):
                return []

            ingestion_integration.register_activity_provider("strava", fetch, linked)

            registered = provider_registry.get("strava")
            assert registered.fetch_window is fetch
            assert registered.linked_user_ids is linked
        finally:
            provider_registry.clear()
