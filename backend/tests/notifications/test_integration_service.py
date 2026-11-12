"""Tests for the notifications surface consumed by other modules."""

import json
import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import modules.notifications.constants as notifications_constants
import modules.notifications.integration_service as notifications_integration


def test_garmin_token_expired_stages_without_committing(mock_db):
    stored = MagicMock(id=uuid.UUID(int=4))
    with patch(
        "modules.notifications.integration_service.notifications_crud.create_notification", return_value=stored
    ) as create:
        notification, ws_message = notifications_integration.create_garmin_token_expired_notification(1, mock_db)

    data = create.call_args.args[0]
    assert data.user_id == 1
    assert data.type == notifications_constants.NotificationType.GARMIN_TOKEN_EXPIRED
    assert notification is stored
    assert ws_message == notifications_constants.GARMIN_UNLINKED_WS_MESSAGE
    mock_db.commit.assert_not_called()


def test_strava_token_expired_stages_without_committing(mock_db):
    stored = MagicMock(id=uuid.UUID(int=5))
    with patch(
        "modules.notifications.integration_service.notifications_crud.create_notification", return_value=stored
    ) as create:
        notification, ws_message = notifications_integration.create_strava_token_expired_notification(1, mock_db)

    data = create.call_args.args[0]
    assert data.user_id == 1
    assert data.type == notifications_constants.NotificationType.STRAVA_TOKEN_EXPIRED
    assert notification is stored
    assert ws_message == notifications_constants.STRAVA_UNLINKED_WS_MESSAGE
    mock_db.commit.assert_not_called()


def test_a_revoked_strava_notice_carries_the_day_the_data_is_deleted(mock_db):
    with patch(
        "modules.notifications.integration_service.notifications_crud.create_notification",
        return_value=MagicMock(id=uuid.UUID(int=5)),
    ) as create:
        notifications_integration.create_strava_token_expired_notification(1, mock_db, delete_on=date(2026, 11, 12))

    data = create.call_args.args[0]
    assert data.type == notifications_constants.NotificationType.STRAVA_TOKEN_EXPIRED
    assert data.options == {"delete_on": "2026-11-12"}


def test_strava_data_deleted_stages_without_committing(mock_db):
    stored = MagicMock(id=uuid.UUID(int=6))
    with patch(
        "modules.notifications.integration_service.notifications_crud.create_notification", return_value=stored
    ) as create:
        notification, ws_message = notifications_integration.create_strava_data_deleted_notification(1, mock_db)

    data = create.call_args.args[0]
    assert data.type == notifications_constants.NotificationType.STRAVA_DATA_DELETED
    assert notification is stored
    assert ws_message == notifications_constants.STRAVA_DATA_DELETED_WS_MESSAGE
    mock_db.commit.assert_not_called()


def test_delete_notifications_naming_user_stages_through_the_crud(mock_db):
    with patch(
        "modules.notifications.integration_service.notifications_crud.delete_notifications_naming_user"
    ) as delete:
        notifications_integration.delete_notifications_naming_user(7, mock_db)

    delete.assert_called_once_with(7, mock_db)
    mock_db.commit.assert_not_called()


def test_the_realtime_hint_is_json_serialisable_and_carries_the_notification_id():
    notification = MagicMock(id=uuid.uuid4())
    with patch("modules.notifications.integration_service.websocket_integration.push_to_user") as push:
        notifications_integration.push_notification(1, notification, "NEW_ACTIVITY_NOTIFICATION")

    hint = push.call_args.args[1]
    assert json.loads(json.dumps(hint))["notification_id"] == str(notification.id)
