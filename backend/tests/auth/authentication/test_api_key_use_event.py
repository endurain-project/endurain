"""Tests for the API-key use event and the subscriber that records it."""

from unittest.mock import MagicMock, patch

import modules.auth.authentication.event_publishers as event_publishers
import modules.auth.authentication.events as events
import modules.auth.authentication.subscribers as subscribers


def test_publishing_sends_only_the_key_id_to_the_bus():
    with patch.object(event_publishers.platform_publisher, "publish") as publish:
        event_publishers.publish_api_key_used("key-1", MagicMock())

    args, kwargs = publish.call_args
    assert args == (events.API_KEY_USED, {"api_key_id": "key-1"})
    assert kwargs["source"] == "api:authenticate_api_key"


def test_the_subscriber_records_the_use_in_its_own_committed_session():
    event = MagicMock()
    db = MagicMock()
    with (
        patch.object(
            subscribers.platform_event_versioning, "parse_payload", return_value=MagicMock(api_key_id="key-1")
        ),
        patch.object(subscribers.core_database, "SessionLocal") as session_local,
        patch.object(subscribers.api_keys_integration, "update_last_used") as update_last_used,
    ):
        session_local.return_value.__enter__.return_value = db
        subscribers.record_api_key_use_for_event(event)

    update_last_used.assert_called_once_with("key-1", db)
    db.commit.assert_called_once()
