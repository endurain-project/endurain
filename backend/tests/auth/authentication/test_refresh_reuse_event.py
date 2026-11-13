"""A refresh token reused outside its grace window stages the notice event with the commit that ends the session."""

import contextlib
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.authentication.event_publishers as authentication_event_publishers
import modules.auth.authentication.events as authentication_events
import modules.auth.authentication.refresh_service as refresh_service

_USER_ID_5 = uuid.UUID(int=5)

_USER_ID = uuid.UUID(int=1)

_REFRESH = "modules.auth.authentication.refresh_service"


def _session():
    return SimpleNamespace(
        id="sid",
        user_id=_USER_ID,
        token_family_id="family",
        refresh_token="hash",
        csrf_token_hash=None,
        rotation_count=0,
        client_type="web",
    )


def _refresh(mock_db, reuse):
    with (
        patch(f"{_REFRESH}.sessions_integration.lock_live_session", return_value=_session()),
        patch(f"{_REFRESH}.server_settings_integration.get_session_policy"),
        patch(f"{_REFRESH}.sessions_integration.validate_session_timeout"),
        patch(f"{_REFRESH}.rotated_refresh_tokens_integration.check_token_reuse", return_value=reuse),
        patch(f"{_REFRESH}.sessions_integration.invalidate_token_family"),
        patch(f"{_REFRESH}.authentication_event_publishers.publish_refresh_reuse_detected") as publish,
        patch(f"{_REFRESH}._replay_rotation"),
        contextlib.suppress(core_exceptions.UnauthenticatedError),
    ):
        refresh_service.refresh_token(
            "127.0.0.1",
            "agent",
            _USER_ID,
            "sid",
            "old",
            datetime(2999, 1, 1, tzinfo=UTC),
            MagicMock(),
            MagicMock(),
            "web",
            mock_db,
        )
    return publish


def test_a_reuse_outside_the_grace_window_tells_the_session_owner(mock_db):
    publish = _refresh(mock_db, (True, False))

    publish.assert_called_once_with(_USER_ID, mock_db)


def test_the_event_is_staged_before_the_commit(mock_db):
    calls = []
    mock_db.commit.side_effect = lambda: calls.append("commit")
    with (
        patch(f"{_REFRESH}.sessions_integration.invalidate_token_family"),
        patch(
            f"{_REFRESH}.authentication_event_publishers.publish_refresh_reuse_detected",
            side_effect=lambda *a, **k: calls.append("publish"),
        ),
        pytest.raises(core_exceptions.InvalidTokenError),
    ):
        refresh_service._end_session_on_reuse(_USER_ID, "family", mock_db)

    assert calls == ["publish", "commit"]


def test_a_replay_inside_the_grace_window_tells_nobody(mock_db):
    publish = _refresh(mock_db, (True, True))

    publish.assert_not_called()


def test_the_event_names_the_user_and_nothing_else(mock_db):
    with patch("modules.auth.authentication.event_publishers.platform_publisher.publish_on_commit") as publish:
        authentication_event_publishers.publish_refresh_reuse_detected(_USER_ID_5, mock_db)

    event_type, payload = publish.call_args.args
    assert event_type == authentication_events.REFRESH_REUSE_DETECTED
    assert payload == {"user_id": str(_USER_ID_5)}
    assert publish.call_args.kwargs["db"] is mock_db
