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


def test_admin_sign_up_approval_stages_one_per_admin(mock_db):
    user = MagicMock(id=9)
    user.name = "New"
    user.username = "new"
    admins = [MagicMock(id=1), MagicMock(id=2)]
    with (
        patch("modules.notifications.integration_service.users_integration.list_admin_users", return_value=admins),
        patch(
            "modules.notifications.integration_service.notifications_crud.create_notification",
            side_effect=[MagicMock(id=10), MagicMock(id=11)],
        ) as create,
    ):
        result = notifications_integration.create_admin_sign_up_approval_notifications(user, mock_db)

    assert [call.args[0].user_id for call in create.call_args_list] == [1, 2]
    assert create.call_args_list[0].args[0].options == {"user_id": 9, "user_name": "New", "user_username": "new"}
    assert [(n.id, message) for n, message in result] == [
        (10, notifications_constants.ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST_WS_MESSAGE),
        (11, notifications_constants.ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST_WS_MESSAGE),
    ]
    mock_db.commit.assert_not_called()


def test_admin_sign_up_approval_with_no_admins_stages_nothing(mock_db):
    with patch("modules.notifications.integration_service.users_integration.list_admin_users", return_value=[]):
        assert notifications_integration.create_admin_sign_up_approval_notifications(MagicMock(), mock_db) == []
