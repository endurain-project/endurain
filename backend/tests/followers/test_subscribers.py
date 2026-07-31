"""Tests for the follower notification subscribers (follower.requested / accepted)."""

from unittest.mock import MagicMock, patch

from infra.events import new_event


def _event(event_type, payload):
    return new_event(event_type, payload, source="test")


class TestOnFollowerRequestedNotify:
    @patch("modules.followers.subscribers.notifications_utils")
    def test_noop_for_non_int_ids(self, mock_notif):
        from modules.followers.subscribers import on_follower_requested_notify

        on_follower_requested_notify(_event("follower.requested", {"requester_user_id": "x", "target_user_id": 2}))

        mock_notif.create_new_follower_request_notification.assert_not_called()

    @patch("modules.followers.subscribers.websocket_utils")
    @patch("modules.followers.subscribers.websocket_manager")
    @patch("modules.followers.subscribers.platform_async_bridge")
    @patch("modules.followers.subscribers.core_database")
    @patch("modules.followers.subscribers.notifications_utils")
    def test_creates_notification_and_dispatches(self, mock_notif, mock_db, mock_bridge, mock_ws_mgr, mock_ws_utils):
        from modules.followers.subscribers import on_follower_requested_notify

        mock_notif.create_new_follower_request_notification.return_value = (
            MagicMock(id=5),
            "NEW_FOLLOWER_REQUEST_NOTIFICATION",
        )

        on_follower_requested_notify(_event("follower.requested", {"requester_user_id": 1, "target_user_id": 2}))

        # Row created for requester=1 -> target=2; websocket push dispatched.
        assert mock_notif.create_new_follower_request_notification.call_args.args[:2] == (1, 2)
        mock_bridge.dispatch.assert_called_once()

    @patch("infra.subscribers.logger")
    @patch("modules.followers.subscribers.core_database")
    @patch("modules.followers.subscribers.notifications_utils")
    def test_swallows_errors(self, mock_notif, mock_db, mock_logger):
        from modules.followers.subscribers import on_follower_requested_notify

        mock_notif.create_new_follower_request_notification.side_effect = RuntimeError("boom")

        # Must not raise — a notification failure never breaks the follow request.
        on_follower_requested_notify(_event("follower.requested", {"requester_user_id": 1, "target_user_id": 2}))

        mock_logger.error.assert_called()


class TestOnFollowerAcceptedNotify:
    @patch("modules.followers.subscribers.notifications_utils")
    def test_noop_for_non_int_ids(self, mock_notif):
        from modules.followers.subscribers import on_follower_accepted_notify

        on_follower_accepted_notify(_event("follower.accepted", {"accepter_user_id": 1, "requester_user_id": None}))

        mock_notif.create_accepted_follower_request_notification.assert_not_called()

    @patch("modules.followers.subscribers.websocket_utils")
    @patch("modules.followers.subscribers.websocket_manager")
    @patch("modules.followers.subscribers.platform_async_bridge")
    @patch("modules.followers.subscribers.core_database")
    @patch("modules.followers.subscribers.notifications_utils")
    def test_creates_notification_and_dispatches(self, mock_notif, mock_db, mock_bridge, mock_ws_mgr, mock_ws_utils):
        from modules.followers.subscribers import on_follower_accepted_notify

        mock_notif.create_accepted_follower_request_notification.return_value = (
            MagicMock(id=7),
            "NEW_FOLLOWER_REQUEST_ACCEPTED_NOTIFICATION",
        )

        on_follower_accepted_notify(_event("follower.accepted", {"accepter_user_id": 1, "requester_user_id": 2}))

        # Row created for accepter=1 -> requester=2; websocket push dispatched.
        assert mock_notif.create_accepted_follower_request_notification.call_args.args[:2] == (1, 2)
        mock_bridge.dispatch.assert_called_once()

    @patch("infra.subscribers.logger")
    @patch("modules.followers.subscribers.core_database")
    @patch("modules.followers.subscribers.notifications_utils")
    def test_swallows_errors(self, mock_notif, mock_db, mock_logger):
        from modules.followers.subscribers import on_follower_accepted_notify

        mock_notif.create_accepted_follower_request_notification.side_effect = RuntimeError("boom")

        on_follower_accepted_notify(_event("follower.accepted", {"accepter_user_id": 1, "requester_user_id": 2}))

        mock_logger.error.assert_called()


class TestRegisterFollowerNotificationSubscribers:
    def test_subscribes_to_both_events(self):
        import modules.followers.events as followers_events
        from modules.followers.subscribers import (
            on_follower_accepted_notify,
            on_follower_requested_notify,
            register_follower_notification_subscribers,
        )

        events = MagicMock()
        register_follower_notification_subscribers(events)

        subscribed = {call.args[0]: call.args[1] for call in events.subscribe.call_args_list}
        assert subscribed[followers_events.FOLLOWER_REQUESTED] is on_follower_requested_notify
        assert subscribed[followers_events.FOLLOWER_ACCEPTED] is on_follower_accepted_notify

    def test_registers_both_durable_handlers(self):
        import modules.followers.events as followers_events
        from modules.followers import subscribers

        registry = MagicMock()
        subscribers.register_follower_notification_durable_handlers(registry)

        registry.register.assert_any_call(
            followers_events.FOLLOWER_REQUESTED,
            subscribers.FOLLOWER_REQUESTED_NOTIFICATION_SUBSCRIBER_ID,
            subscribers.notify_follower_requested_for_event,
        )
        registry.register.assert_any_call(
            followers_events.FOLLOWER_ACCEPTED,
            subscribers.FOLLOWER_ACCEPTED_NOTIFICATION_SUBSCRIBER_ID,
            subscribers.notify_follower_accepted_for_event,
        )
