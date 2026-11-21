"""The notifications surface other modules consume: staged notices, the cleanup of an erased user and the push."""

from datetime import date

import jasil.runtime as platform_runtime
from jasil.testing import capture_hints
from sqlalchemy import select

import modules.notifications.constants as notifications_constants
import modules.notifications.integration_service as notifications_integration
import modules.notifications.models as notifications_models
import modules.websocket.keys as websocket_keys
from tests._factories.notifications import make_notification_of
from tests._factories.users import make_user

_TYPES = notifications_constants.NotificationType


def _stored(db) -> list[notifications_models.Notification]:
    return list(db.scalars(select(notifications_models.Notification)))


class TestStagedNotices:
    def test_a_garmin_notice_is_staged_for_the_user_and_not_committed(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()

        with committed_sessions() as db:
            notification, ws_message = notifications_integration.create_garmin_token_expired_notification(user.id, db)
            assert [(n.id, n.user_id, n.type) for n in _stored(db)] == [
                (notification.id, user.id, _TYPES.GARMIN_TOKEN_EXPIRED.stored)
            ]
            db.rollback()
            assert _stored(db) == []
        assert ws_message == notifications_constants.GARMIN_UNLINKED_WS_MESSAGE

    def test_a_strava_notice_carries_no_day_when_the_token_was_only_rejected(self, db):
        user = make_user(db)

        notification, ws_message = notifications_integration.create_strava_token_expired_notification(user.id, db)

        assert notification.type == _TYPES.STRAVA_TOKEN_EXPIRED
        assert notification.options.delete_on is None
        assert ws_message == notifications_constants.STRAVA_UNLINKED_WS_MESSAGE

    def test_a_revoked_strava_notice_carries_the_day_the_data_is_deleted(self, db):
        user = make_user(db)

        notification, _ = notifications_integration.create_strava_token_expired_notification(
            user.id, db, delete_on=date(2026, 11, 12)
        )

        assert notification.options.delete_on == date(2026, 11, 12)
        (row,) = _stored(db)
        assert row.options == {"delete_on": "2026-11-12"}

    def test_a_strava_data_deleted_notice_is_staged_for_the_user(self, db):
        user = make_user(db)

        notification, ws_message = notifications_integration.create_strava_data_deleted_notification(user.id, db)

        assert (notification.user_id, notification.type) == (user.id, _TYPES.STRAVA_DATA_DELETED)
        assert ws_message == notifications_constants.STRAVA_DATA_DELETED_WS_MESSAGE


def test_erasing_a_user_removes_the_notifications_that_name_them(db):
    owner, erased = make_user(db), make_user(db)
    make_notification_of(
        db,
        owner.id,
        _TYPES.NEW_FOLLOWER_REQUEST,
        {"user_id": str(erased.id), "user_name": erased.name, "user_username": erased.username},
    )
    kept = make_notification_of(db, owner.id, _TYPES.GARMIN_TOKEN_EXPIRED)

    notifications_integration.delete_notifications_naming_user(erased.id, db)

    assert [n.id for n in _stored(db)] == [kept.id]


def test_the_push_reaches_the_users_channel_with_the_message_and_the_notification_id(db):
    user = make_user(db)
    notification = make_notification_of(db, user.id, _TYPES.GARMIN_TOKEN_EXPIRED)
    hints = capture_hints(platform_runtime.get_active_platform())

    notifications_integration.push_notification(user.id, notification, "GARMIN_TOKEN_EXPIRED_NOTIFICATION")

    assert hints == [
        (
            websocket_keys.user_key(user.id),
            {"message": "GARMIN_TOKEN_EXPIRED_NOTIFICATION", "notification_id": str(notification.id)},
        )
    ]
