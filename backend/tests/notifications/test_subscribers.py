"""The event consumers that raise notifications, on the real database.

Each is driven the two ways production does: published on the bus, where a failure is absorbed, and called through the
durable registry, where it propagates so the job retries. The outcome is the stored notification rows and the
realtime hint the recipient's browser would get.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

import jasil.runtime as platform_runtime
import pytest
from jasil.events import Event, new_event
from jasil.jobs.registry import JobHandlerRegistry
from jasil.testing import capture_hints
from sqlalchemy import select

import modules.activities.activity.events as activity_events
import modules.auth.account_security.events as account_security_events
import modules.auth.authentication.events as authentication_events
import modules.auth.identity_providers.events as idp_events
import modules.auth.known_devices.events as known_devices_events
import modules.auth.mfa_backup_codes.events as backup_codes_events
import modules.auth.password_reset_tokens.events as password_reset_events
import modules.auth.sign_up_tokens.events as sign_up_events
import modules.followers.events as followers_events
import modules.notifications.constants as notifications_constants
import modules.notifications.models as notifications_models
import modules.notifications.subscriber_registry as notifications_subscriber_registry
import modules.notifications.subscribers as notifications_subscribers
import modules.users.users.events as users_events
import modules.users.users.schema as users_schema
import modules.websocket.keys as websocket_keys
from tests._factories.identity_links import make_identity_provider
from tests._factories.notifications import make_notification_of
from tests._factories.users import make_user

_TYPES = notifications_constants.NotificationType
_CHANGE = account_security_events.AccountSecurityChange


@dataclass(frozen=True)
class Delivery:
    """One event a notification consumer reacts to.

    Attributes:
        event_type: The event's type.
        subscriber_id: The consumer's durable subscriber id.
        payload: Builds the event payload from the recipient's id, the named user's id and a provider id.
        notification_type: The notification the consumer stores.
        ws_message: The realtime message it pushes.
        options: The options it stores, given the named user and the provider's name.
    """

    event_type: str
    subscriber_id: str
    payload: Callable[[str, str, str], dict]
    notification_type: notifications_constants.NotificationType
    ws_message: str
    options: Callable[[users_schema.UserRead, str], dict]


def _naming(named: users_schema.UserRead, _idp_name: str) -> dict:
    return {"user_id": str(named.id), "user_name": named.name, "user_username": named.username}


def _change(change: _CHANGE, **extra: object) -> Callable[[users_schema.UserRead, str], dict]:
    return lambda _named, _idp_name: {"change": change.value, **extra}


_ACTIVITY_ID = "11111111-1111-4111-8111-111111111111"
_SECURITY = notifications_constants.ACCOUNT_SECURITY_CHANGED_WS_MESSAGE

_DELIVERIES = {
    "new-activity": Delivery(
        activity_events.ACTIVITY_CREATED,
        notifications_subscribers.ACTIVITY_NOTIFICATION_SUBSCRIBER_ID,
        lambda me, _other, _idp: {"activity_id": _ACTIVITY_ID, "user_id": me},
        _TYPES.NEW_ACTIVITY,
        notifications_constants.NEW_ACTIVITY_WS_MESSAGE,
        lambda _named, _idp_name: {"activity_id": _ACTIVITY_ID},
    ),
    "duplicate-activity": Delivery(
        activity_events.ACTIVITY_CREATED,
        notifications_subscribers.ACTIVITY_NOTIFICATION_SUBSCRIBER_ID,
        lambda me, _other, _idp: {"activity_id": _ACTIVITY_ID, "user_id": me, "duplicate_start_time": True},
        _TYPES.DUPLICATE_ACTIVITY,
        notifications_constants.DUPLICATE_ACTIVITY_WS_MESSAGE,
        lambda _named, _idp_name: {"activity_id": _ACTIVITY_ID},
    ),
    "follow-requested": Delivery(
        followers_events.FOLLOWER_REQUESTED,
        notifications_subscribers.FOLLOWER_REQUESTED_NOTIFICATION_SUBSCRIBER_ID,
        lambda me, other, _idp: {"requester_user_id": other, "target_user_id": me},
        _TYPES.NEW_FOLLOWER_REQUEST,
        notifications_constants.NEW_FOLLOWER_REQUEST_WS_MESSAGE,
        _naming,
    ),
    "follow-accepted": Delivery(
        followers_events.FOLLOWER_ACCEPTED,
        notifications_subscribers.FOLLOWER_ACCEPTED_NOTIFICATION_SUBSCRIBER_ID,
        lambda me, other, _idp: {"accepter_user_id": other, "requester_user_id": me},
        _TYPES.NEW_FOLLOWER_REQUEST_ACCEPTED,
        notifications_constants.NEW_FOLLOWER_REQUEST_ACCEPTED_WS_MESSAGE,
        _naming,
    ),
    "idp-linked": Delivery(
        idp_events.IDP_LINKED,
        notifications_subscribers.IDP_LINKED_NOTIFICATION_SUBSCRIBER_ID,
        lambda me, _other, idp: {"user_id": me, "idp_id": idp},
        _TYPES.IDP_LINKED,
        notifications_constants.IDP_LINKED_WS_MESSAGE,
        lambda _named, idp_name: {"idp_id": "", "idp_name": idp_name},
    ),
    "account-security-changed": Delivery(
        account_security_events.ACCOUNT_SECURITY_CHANGED,
        notifications_subscribers.ACCOUNT_SECURITY_CHANGED_NOTIFICATION_SUBSCRIBER_ID,
        lambda me, _other, _idp: {
            "user_id": me,
            "change": _CHANGE.ROLE_CHANGED_BY_ADMIN.value,
            "access_type": "admin",
        },
        _TYPES.ACCOUNT_SECURITY_CHANGED,
        _SECURITY,
        _change(_CHANGE.ROLE_CHANGED_BY_ADMIN, access_type="admin"),
    ),
    "account-security-idp-unlinked": Delivery(
        account_security_events.ACCOUNT_SECURITY_CHANGED,
        notifications_subscribers.ACCOUNT_SECURITY_CHANGED_NOTIFICATION_SUBSCRIBER_ID,
        lambda me, _other, idp: {"user_id": me, "change": _CHANGE.IDENTITY_PROVIDER_UNLINKED.value, "idp_id": idp},
        _TYPES.ACCOUNT_SECURITY_CHANGED,
        _SECURITY,
        lambda _named, idp_name: {
            "change": _CHANGE.IDENTITY_PROVIDER_UNLINKED.value,
            "idp_id": "",
            "idp_name": idp_name,
        },
    ),
    "password-reset-completed": Delivery(
        password_reset_events.PASSWORD_RESET_COMPLETED,
        notifications_subscribers.PASSWORD_RESET_COMPLETED_NOTIFICATION_SUBSCRIBER_ID,
        lambda me, _other, _idp: {"user_id": me},
        _TYPES.ACCOUNT_SECURITY_CHANGED,
        _SECURITY,
        _change(_CHANGE.PASSWORD_RESET),
    ),
    "account-locked": Delivery(
        authentication_events.ACCOUNT_LOCKED,
        notifications_subscribers.ACCOUNT_LOCKED_NOTIFICATION_SUBSCRIBER_ID,
        lambda me, _other, _idp: {"user_id": me},
        _TYPES.ACCOUNT_SECURITY_CHANGED,
        _SECURITY,
        _change(_CHANGE.ACCOUNT_LOCKED),
    ),
    "mfa-locked": Delivery(
        authentication_events.MFA_LOCKED,
        notifications_subscribers.MFA_LOCKED_NOTIFICATION_SUBSCRIBER_ID,
        lambda me, _other, _idp: {"user_id": me},
        _TYPES.ACCOUNT_SECURITY_CHANGED,
        _SECURITY,
        _change(_CHANGE.MFA_LOCKED),
    ),
    "step-up-session-ended": Delivery(
        account_security_events.STEP_UP_SESSION_ENDED,
        notifications_subscribers.STEP_UP_SESSION_ENDED_NOTIFICATION_SUBSCRIBER_ID,
        lambda me, _other, _idp: {"user_id": me},
        _TYPES.ACCOUNT_SECURITY_CHANGED,
        _SECURITY,
        _change(_CHANGE.STEP_UP_SESSION_ENDED),
    ),
    "step-up-locked": Delivery(
        account_security_events.STEP_UP_LOCKED,
        notifications_subscribers.STEP_UP_LOCKED_NOTIFICATION_SUBSCRIBER_ID,
        lambda me, _other, _idp: {"user_id": me},
        _TYPES.ACCOUNT_SECURITY_CHANGED,
        _SECURITY,
        _change(_CHANGE.STEP_UP_LOCKED),
    ),
    "refresh-reuse": Delivery(
        authentication_events.REFRESH_REUSE_DETECTED,
        notifications_subscribers.REFRESH_REUSE_NOTIFICATION_SUBSCRIBER_ID,
        lambda me, _other, _idp: {"user_id": me},
        _TYPES.ACCOUNT_SECURITY_CHANGED,
        _SECURITY,
        _change(_CHANGE.REFRESH_TOKEN_REUSE_DETECTED),
    ),
    "backup-code-used": Delivery(
        backup_codes_events.BACKUP_CODE_USED,
        notifications_subscribers.BACKUP_CODE_USED_NOTIFICATION_SUBSCRIBER_ID,
        lambda me, _other, _idp: {"user_id": me, "backup_codes_remaining": 4},
        _TYPES.ACCOUNT_SECURITY_CHANGED,
        _SECURITY,
        _change(_CHANGE.BACKUP_CODE_USED, backup_codes_remaining=4),
    ),
    "new-device-sign-in": Delivery(
        known_devices_events.NEW_DEVICE_SIGN_IN,
        notifications_subscribers.NEW_DEVICE_SIGN_IN_NOTIFICATION_SUBSCRIBER_ID,
        lambda me, _other, _idp: {
            "user_id": me,
            "browser": "Firefox",
            "operating_system": "Linux",
            "device_type": "PC",
            "ip_address": "10.0.0.1",
            "method": "password",
            "signed_in_at": "2026-01-01T10:00:00Z",
        },
        _TYPES.NEW_DEVICE_SIGN_IN,
        notifications_constants.NEW_DEVICE_SIGN_IN_WS_MESSAGE,
        lambda _named, _idp_name: {"browser": "Firefox", "operating_system": "Linux", "ip_address": "10.0.0.1"},
    ),
    "sign-up-approval": Delivery(
        sign_up_events.SIGN_UP_APPROVAL_REQUESTED,
        notifications_subscribers.ADMIN_SIGN_UP_APPROVAL_NOTIFICATION_SUBSCRIBER_ID,
        lambda me, other, _idp: {"user_id": other, "admin_user_id": me},
        _TYPES.ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST,
        notifications_constants.ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST_WS_MESSAGE,
        _naming,
    ),
    "admin-promoted": Delivery(
        users_events.USERS_ADMIN_PROMOTED,
        notifications_subscribers.ADMIN_USER_PROMOTED_NOTIFICATION_SUBSCRIBER_ID,
        lambda me, other, _idp: {"user_id": other, "admin_user_id": me},
        _TYPES.ADMIN_USER_PROMOTED,
        notifications_constants.ADMIN_USER_PROMOTED_WS_MESSAGE,
        _naming,
    ),
}


@dataclass(frozen=True)
class Scene:
    """The users and provider a delivery's event names.

    Attributes:
        me: The recipient.
        other: The user the notification names, where it names one.
        idp_id: A stored provider.
        idp_name: That provider's name.
    """

    me: users_schema.UserRead
    other: users_schema.UserRead
    idp_id: uuid.UUID
    idp_name: str

    def event(self, delivery: Delivery, *, event_id: str | None = None, recipient_id: uuid.UUID | None = None) -> Event:
        """Build the delivery's event; ``recipient_id`` replaces the recipient, to name a user that is gone."""
        payload = delivery.payload(str(recipient_id or self.me.id), str(self.other.id), str(self.idp_id))
        return new_event(delivery.event_type, payload, source="test", event_id=event_id)

    def expected_options(self, delivery: Delivery) -> dict:
        """The options the consumer is expected to store."""
        options = delivery.options(self.other, self.idp_name)
        return {**options, "idp_id": str(self.idp_id)} if "idp_id" in options else options


@pytest.fixture
def scene(db) -> Scene:
    idp_id = make_identity_provider(db, "keycloak")
    return Scene(make_user(db), make_user(db), idp_id, "Provider keycloak")


@pytest.fixture
def hints():
    return capture_hints(platform_runtime.get_active_platform())


@pytest.fixture
def durable() -> JobHandlerRegistry:
    registry = JobHandlerRegistry()
    notifications_subscriber_registry.register_durable_handlers(registry)
    return registry


@pytest.fixture
def bus():
    events = platform_runtime.get_active_platform().events
    notifications_subscriber_registry.register_bus_subscribers(events)
    return events


def _stored(db) -> list[notifications_models.Notification]:
    return list(db.scalars(select(notifications_models.Notification)))


_EVERY_DELIVERY = pytest.mark.parametrize("delivery", _DELIVERIES.values(), ids=_DELIVERIES.keys())


@_EVERY_DELIVERY
def test_an_event_published_on_the_bus_stores_the_notification_and_pushes_it(db, scene, hints, bus, delivery):
    bus.publish(scene.event(delivery))

    (row,) = _stored(db)
    assert (row.user_id, row.type, row.read) == (scene.me.id, delivery.notification_type.stored, False)
    assert row.options == scene.expected_options(delivery)
    assert hints == [
        (
            websocket_keys.user_key(scene.me.id),
            {"message": delivery.ws_message, "notification_id": str(row.id)},
        )
    ]


@_EVERY_DELIVERY
def test_a_redelivered_event_stores_and_pushes_once(db, scene, hints, durable, delivery):
    handler = durable.get(delivery.subscriber_id)
    event = scene.event(delivery)

    handler(event)
    handler(event)

    assert len(_stored(db)) == 1
    assert len(hints) == 1


@_EVERY_DELIVERY
def test_an_event_for_a_user_that_is_gone_is_dropped_without_failing_the_job(db, scene, hints, durable, delivery):
    durable.get(delivery.subscriber_id)(scene.event(delivery, recipient_id=uuid.uuid4()))

    assert _stored(db) == []
    assert hints == []


def test_a_leg_of_a_multisport_activity_creates_no_notification_while_its_parent_does(db, scene, hints, durable):
    handler = durable.get(notifications_subscribers.ACTIVITY_NOTIFICATION_SUBSCRIBER_ID)
    parent_id = str(uuid.uuid4())

    def created(activity_id: str, parent: str | None) -> Event:
        payload = {"activity_id": activity_id, "user_id": str(scene.me.id), "parent_activity_id": parent}
        return new_event(activity_events.ACTIVITY_CREATED, payload, source="test")

    for _ in range(3):
        handler(created(str(uuid.uuid4()), parent_id))
    assert _stored(db) == []
    assert hints == []

    handler(created(parent_id, None))

    (row,) = _stored(db)
    assert (row.user_id, row.type, row.options) == (
        scene.me.id,
        _TYPES.NEW_ACTIVITY.stored,
        {"activity_id": parent_id},
    )


def test_every_consumer_is_registered_for_both_delivery_paths(durable):
    registered = durable.subscriber_ids()

    assert {d.subscriber_id for d in _DELIVERIES.values()} < registered
    assert notifications_subscribers.FOLLOWER_REQUEST_REMOVED_NOTIFICATION_SUBSCRIBER_ID in registered
    assert len(registered) == 16


def test_a_malformed_event_fails_the_durable_job_and_is_absorbed_on_the_bus(db, hints, durable, bus):
    event = new_event(activity_events.ACTIVITY_CREATED, {"activity_id": "x"}, source="test")

    with pytest.raises(ValueError, match="activity_id"):
        durable.get(notifications_subscribers.ACTIVITY_NOTIFICATION_SUBSCRIBER_ID)(event)
    bus.publish(event)

    assert _stored(db) == []
    assert hints == []


class TestFollowRequestRemoved:
    @staticmethod
    def _event(requester, target) -> Event:
        return new_event(
            followers_events.FOLLOWER_REQUEST_REMOVED,
            {"requester_user_id": str(requester.id), "target_user_id": str(target.id)},
            source="test",
        )

    @staticmethod
    def _request_notification(db, requester, target):
        return make_notification_of(
            db,
            target.id,
            _TYPES.NEW_FOLLOWER_REQUEST,
            {"user_id": str(requester.id), "user_name": requester.name, "user_username": requester.username},
        )

    def test_the_request_notification_is_taken_back_and_the_target_told_once(self, db, hints, bus):
        requester, target, other = make_user(db), make_user(db), make_user(db)
        self._request_notification(db, requester, target)
        kept = self._request_notification(db, other, target)
        event = self._event(requester, target)

        bus.publish(event)
        bus.publish(event)

        assert [n.id for n in _stored(db)] == [kept.id]
        assert hints == [
            (
                websocket_keys.user_key(target.id),
                {"message": notifications_constants.NEW_FOLLOWER_REQUEST_REMOVED_WS_MESSAGE},
            )
        ]

    def test_nothing_is_pushed_when_there_was_nothing_to_take_back(self, db, hints, durable):
        requester, target = make_user(db), make_user(db)

        durable.get(notifications_subscribers.FOLLOWER_REQUEST_REMOVED_NOTIFICATION_SUBSCRIBER_ID)(
            self._event(requester, target)
        )

        assert hints == []
