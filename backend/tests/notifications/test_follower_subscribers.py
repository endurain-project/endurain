"""Tests for follower notification event consumers."""

from unittest.mock import MagicMock, patch

from infra.events import new_event


def _event(event_type, payload):
    return new_event(event_type, payload, source="test")


class TestOnFollowerRequestedNotify:
    @patch("modules.notifications.subscribers.notifications_integration")
    def test_noop_for_non_int_ids(self, mock_notif):
        from modules.notifications.subscribers import on_follower_requested_notify

        on_follower_requested_notify(_event("follower.requested", {"requester_user_id": "x", "target_user_id": 2}))
        mock_notif.create_follow_request_notification.assert_not_called()

    @patch("modules.notifications.subscribers.websocket_integration")
    @patch("modules.notifications.subscribers.core_async_bridge")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_integration")
    def test_creates_notification_and_dispatches(self, mock_notif, mock_db, mock_bridge, mock_ws):
        from modules.notifications.subscribers import on_follower_requested_notify

        mock_notif.create_follow_request_notification.return_value = (
            MagicMock(id=5),
            "NEW_FOLLOWER_REQUEST_NOTIFICATION",
        )
        on_follower_requested_notify(_event("follower.requested", {"requester_user_id": 1, "target_user_id": 2}))
        assert mock_notif.create_follow_request_notification.call_args.args[:2] == (1, 2)
        mock_bridge.dispatch.assert_called_once()

    @patch("infra.subscribers.logger")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_integration")
    def test_swallows_errors(self, mock_notif, mock_db, mock_logger):
        from modules.notifications.subscribers import on_follower_requested_notify

        mock_notif.create_follow_request_notification.side_effect = RuntimeError("boom")
        on_follower_requested_notify(_event("follower.requested", {"requester_user_id": 1, "target_user_id": 2}))
        mock_logger.error.assert_called()


class TestOnFollowerAcceptedNotify:
    @patch("modules.notifications.subscribers.notifications_integration")
    def test_noop_for_non_int_ids(self, mock_notif):
        from modules.notifications.subscribers import on_follower_accepted_notify

        on_follower_accepted_notify(_event("follower.accepted", {"accepter_user_id": 1, "requester_user_id": None}))
        mock_notif.create_follow_accepted_notification.assert_not_called()

    @patch("modules.notifications.subscribers.websocket_integration")
    @patch("modules.notifications.subscribers.core_async_bridge")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_integration")
    def test_creates_notification_and_dispatches(self, mock_notif, mock_db, mock_bridge, mock_ws):
        from modules.notifications.subscribers import on_follower_accepted_notify

        mock_notif.create_follow_accepted_notification.return_value = (
            MagicMock(id=7),
            "NEW_FOLLOWER_REQUEST_ACCEPTED_NOTIFICATION",
        )
        on_follower_accepted_notify(_event("follower.accepted", {"accepter_user_id": 1, "requester_user_id": 2}))
        assert mock_notif.create_follow_accepted_notification.call_args.args[:2] == (1, 2)
        mock_bridge.dispatch.assert_called_once()

    @patch("infra.subscribers.logger")
    @patch("modules.notifications.subscribers.core_database")
    @patch("modules.notifications.subscribers.notifications_integration")
    def test_swallows_errors(self, mock_notif, mock_db, mock_logger):
        from modules.notifications.subscribers import on_follower_accepted_notify

        mock_notif.create_follow_accepted_notification.side_effect = RuntimeError("boom")
        on_follower_accepted_notify(_event("follower.accepted", {"accepter_user_id": 1, "requester_user_id": 2}))
        mock_logger.error.assert_called()


class TestRegisterFollowerNotificationConsumers:
    def test_subscribes_to_both_events(self):
        import modules.followers.events as follower_events
        from modules.notifications import subscribers

        events = MagicMock()
        subscribers.register_notification_subscribers(events)
        subscribed = {call.args[0]: call.args[1] for call in events.subscribe.call_args_list}
        assert subscribed[follower_events.FOLLOWER_REQUESTED] is subscribers.on_follower_requested_notify
        assert subscribed[follower_events.FOLLOWER_ACCEPTED] is subscribers.on_follower_accepted_notify

    def test_registers_both_durable_handlers(self):
        import modules.followers.events as follower_events
        from modules.notifications import subscribers

        registry = MagicMock()
        subscribers.register_notification_durable_handlers(registry)
        registry.register.assert_any_call(
            follower_events.FOLLOWER_REQUESTED,
            subscribers.FOLLOWER_REQUESTED_NOTIFICATION_SUBSCRIBER_ID,
            subscribers.notify_follower_requested_for_event,
        )
        registry.register.assert_any_call(
            follower_events.FOLLOWER_ACCEPTED,
            subscribers.FOLLOWER_ACCEPTED_NOTIFICATION_SUBSCRIBER_ID,
            subscribers.notify_follower_accepted_for_event,
        )
