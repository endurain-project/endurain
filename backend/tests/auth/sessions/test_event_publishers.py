"""Tests for the sessions event publishers."""

from unittest.mock import patch

import core.event_metadata as core_event_metadata
import modules.auth.sessions.event_publishers as sessions_event_publishers
import modules.auth.sessions.events as sessions_events


@patch("modules.auth.sessions.event_publishers.platform_publisher")
def test_a_revocation_is_staged_on_the_callers_transaction(mock_publisher):
    db = object()

    sessions_event_publishers.publish_sessions_revoked(7, db, session_id="s1")

    mock_publisher.publish_on_commit.assert_called_once()
    args, kwargs = mock_publisher.publish_on_commit.call_args
    assert args[0] == sessions_events.SESSIONS_REVOKED
    assert args[1] == {"user_id": 7, "session_id": "s1", "except_session_id": None}
    assert kwargs["metadata"] == {core_event_metadata.META_USER_ID: 7}
    assert kwargs["db"] is db
    assert kwargs["schema_version"] == sessions_events.SessionsRevokedPayload.SCHEMA_VERSION
