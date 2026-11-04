"""Tests for the notifications surface consumed by other modules."""

from unittest.mock import MagicMock, patch

import modules.notifications.constants as notifications_constants
import modules.notifications.integration_service as notifications_integration


def test_garmin_token_expired_stages_without_committing(mock_db):
    stored = MagicMock(id=4)
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
    stored = MagicMock(id=5)
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
