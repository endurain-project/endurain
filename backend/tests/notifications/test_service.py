"""The notifications application layer on the real database: the user's reads and writes, retention and creation."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

import core.database as core_database
import core.exceptions as core_exceptions
import modules.notifications.constants as notifications_constants
import modules.notifications.models as notifications_models
import modules.notifications.service as notifications_service
import modules.server_settings.models as server_settings_models
from tests._factories.identity_links import make_identity_provider
from tests._factories.notifications import make_notification, make_notification_of
from tests._factories.users import make_user

_NEW_ACTIVITY = notifications_constants.NotificationType.NEW_ACTIVITY
_TYPES = notifications_constants.NotificationType


def _activity(db, user_id, **kwargs):
    return make_notification_of(db, user_id, _NEW_ACTIVITY, {"activity_id": str(uuid.uuid4())}, **kwargs)


def _stored(db, user_id=None) -> list[notifications_models.Notification]:
    query = select(notifications_models.Notification)
    if user_id is not None:
        query = query.where(notifications_models.Notification.user_id == user_id)
    return list(db.scalars(query))


class TestReads:
    def test_the_unread_count_counts_only_the_users_unread_notifications(self, db):
        user, other = make_user(db), make_user(db)
        _activity(db, user.id)
        _activity(db, user.id, read=True)
        _activity(db, other.id)

        assert notifications_service.count_unread_notifications(user.id, db) == 1

    def test_a_notification_is_returned_to_its_owner_and_missing_for_anyone_else(self, db):
        owner, other = make_user(db), make_user(db)
        notification = make_notification(db, owner.id)

        assert notifications_service.get_notification(notification.id, owner.id, db) == notification
        with pytest.raises(core_exceptions.NotFoundError):
            notifications_service.get_notification(notification.id, other.id, db)

    def test_the_list_over_fetches_one_row_to_know_whether_another_slice_follows(self, db):
        user = make_user(db)
        base = datetime(2024, 1, 1, tzinfo=UTC)
        rows = [_activity(db, user.id, created_at=base + timedelta(days=d)) for d in range(3)]

        first = notifications_service.list_notifications(user.id, db, cursor=None, num_records=2)
        second = notifications_service.list_notifications(user.id, db, cursor=first.next_cursor, num_records=2)

        assert [n.id for n in first.items] == [rows[2].id, rows[1].id]
        assert first.next_cursor is not None
        assert [n.id for n in second.items] == [rows[0].id]
        assert second.next_cursor is None

    def test_a_slice_that_ends_exactly_at_the_last_row_has_no_next_cursor(self, db):
        user = make_user(db)
        _activity(db, user.id)
        _activity(db, user.id)

        page = notifications_service.list_notifications(user.id, db, cursor=None, num_records=2)

        assert len(page.items) == 2
        assert page.next_cursor is None

    def test_a_cursor_the_server_did_not_issue_is_refused(self, db):
        with pytest.raises(core_exceptions.InvalidInputError):
            notifications_service.list_notifications(make_user(db).id, db, cursor="not-a-cursor", num_records=2)


class TestWrites:
    def test_marking_one_read_commits_it_and_refuses_another_users(self, committed_sessions):
        with committed_sessions() as db:
            owner, other = make_user(db), make_user(db)
            notification = make_notification(db, owner.id)
            db.commit()

        with committed_sessions() as db:
            with pytest.raises(core_exceptions.NotFoundError):
                notifications_service.mark_notification_as_read(notification.id, other.id, db)
            notifications_service.mark_notification_as_read(notification.id, owner.id, db)

        with committed_sessions() as db:
            assert db.get(notifications_models.Notification, notification.id).read is True

    def test_marking_several_read_commits_the_users_and_skips_the_rest(self, committed_sessions):
        with committed_sessions() as db:
            user, other = make_user(db), make_user(db)
            mine, theirs = _activity(db, user.id), _activity(db, other.id)
            db.commit()

        with committed_sessions() as db:
            notifications_service.mark_notifications_as_read([mine.id, theirs.id, uuid.uuid4()], user.id, db)

        with committed_sessions() as db:
            assert {n.id: n.read for n in _stored(db)} == {mine.id: True, theirs.id: False}

    def test_marking_all_read_commits_every_notification_of_the_user(self, committed_sessions):
        with committed_sessions() as db:
            user, other = make_user(db), make_user(db)
            _activity(db, user.id)
            _activity(db, user.id)
            _activity(db, other.id)
            db.commit()

        with committed_sessions() as db:
            notifications_service.mark_all_notifications_as_read(user.id, db)

        with committed_sessions() as db:
            assert notifications_service.count_unread_notifications(user.id, db) == 0
            assert notifications_service.count_unread_notifications(other.id, db) == 1

    def test_deleting_commits_the_users_notification_and_refuses_another_users(self, committed_sessions):
        with committed_sessions() as db:
            owner, other = make_user(db), make_user(db)
            notification = make_notification(db, owner.id)
            db.commit()

        with committed_sessions() as db:
            with pytest.raises(core_exceptions.NotFoundError):
                notifications_service.delete_notification(notification.id, other.id, db)
            assert len(_stored(db)) == 1
            notifications_service.delete_notification(notification.id, owner.id, db)

        with committed_sessions() as db:
            assert _stored(db) == []


class TestRetention:
    @staticmethod
    def _retention(db, days: int) -> None:
        db.execute(update(server_settings_models.ServerSettings).values(read_notification_retention_days=days))
        db.flush()

    def test_read_notifications_older_than_the_retention_are_deleted(self, db):
        user = make_user(db)
        self._retention(db, 30)
        now = datetime.now(UTC)
        stale = _activity(db, user.id, read=True, created_at=now - timedelta(days=31))
        kept = [
            _activity(db, user.id, read=True, created_at=now - timedelta(days=29)),
            _activity(db, user.id, read=False, created_at=now - timedelta(days=60)),
        ]

        removed = notifications_service.delete_read_notifications(db)

        assert removed == 1
        assert {n.id for n in _stored(db)} == {n.id for n in kept}
        assert stale.id not in {n.id for n in _stored(db)}

    def test_a_purge_larger_than_a_batch_runs_in_several_batches(self, db, monkeypatch):
        monkeypatch.setattr(core_database, "PURGE_BATCH_SIZE", 2)
        user = make_user(db)
        self._retention(db, 1)
        old = datetime.now(UTC) - timedelta(days=5)
        for _ in range(5):
            _activity(db, user.id, read=True, created_at=old)

        assert notifications_service.delete_read_notifications(db) == 5
        assert _stored(db) == []

    def test_zero_days_disables_pruning(self, db):
        user = make_user(db)
        self._retention(db, 0)
        _activity(db, user.id, read=True, created_at=datetime(2000, 1, 1, tzinfo=UTC))

        assert notifications_service.delete_read_notifications(db) == 0
        assert len(_stored(db)) == 1


class TestRecordedEvents:
    """The event-driven creators: what each stores, and that a redelivered event stores nothing more."""

    @staticmethod
    def _options(db, user_id, notification_type) -> dict:
        (row,) = [n for n in _stored(db, user_id) if n.type == notification_type.stored]
        return row.options

    def test_a_new_activity_notification_carries_the_activity(self, db):
        user = make_user(db)
        activity_id = uuid.uuid4()

        notification, ws_message, created = notifications_service.create_activity_created_notification(
            user.id, activity_id, str(uuid.uuid4()), db
        )

        assert (notification.type, ws_message, created) == (_TYPES.NEW_ACTIVITY, "NEW_ACTIVITY_NOTIFICATION", True)
        assert self._options(db, user.id, _TYPES.NEW_ACTIVITY) == {"activity_id": str(activity_id)}

    def test_a_redelivered_event_reports_not_created_and_stores_nothing_more(self, db):
        user = make_user(db)
        event_id = str(uuid.uuid4())
        first, *_ = notifications_service.create_activity_created_notification(user.id, uuid.uuid4(), event_id, db)

        replay, _, created = notifications_service.create_activity_created_notification(
            user.id, uuid.uuid4(), event_id, db
        )

        assert created is False
        assert replay.id == first.id
        assert len(_stored(db)) == 1

    def test_a_follow_request_names_the_requester_and_belongs_to_the_target(self, db):
        requester, target = make_user(db), make_user(db)

        _, ws_message, created = notifications_service.create_follow_request_notification(
            requester.id, target.id, str(uuid.uuid4()), db
        )

        assert (ws_message, created) == (notifications_constants.NEW_FOLLOWER_REQUEST_WS_MESSAGE, True)
        assert self._options(db, target.id, _TYPES.NEW_FOLLOWER_REQUEST) == {
            "user_id": str(requester.id),
            "user_name": requester.name,
            "user_username": requester.username,
        }
        assert _stored(db, requester.id) == []

    def test_a_follow_acceptance_names_the_accepter_and_belongs_to_the_requester(self, db):
        accepter, requester = make_user(db), make_user(db)

        _, ws_message, _ = notifications_service.create_follow_accepted_notification(
            accepter.id, requester.id, str(uuid.uuid4()), db
        )

        assert ws_message == notifications_constants.NEW_FOLLOWER_REQUEST_ACCEPTED_WS_MESSAGE
        assert self._options(db, requester.id, _TYPES.NEW_FOLLOWER_REQUEST_ACCEPTED)["user_id"] == str(accepter.id)

    def test_a_sign_up_approval_names_the_new_user_and_belongs_to_the_admin(self, db):
        new_user, admin = make_user(db), make_user(db)

        notifications_service.create_admin_sign_up_approval_notification(new_user.id, admin.id, str(uuid.uuid4()), db)

        assert self._options(db, admin.id, _TYPES.ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST)["user_id"] == str(new_user.id)

    def test_an_admin_promotion_names_the_promoted_user_and_belongs_to_the_admin(self, db):
        promoted, admin = make_user(db), make_user(db)

        notifications_service.create_admin_user_promoted_notification(promoted.id, admin.id, str(uuid.uuid4()), db)

        assert self._options(db, admin.id, _TYPES.ADMIN_USER_PROMOTED)["user_id"] == str(promoted.id)

    @pytest.mark.parametrize(
        "create",
        [
            lambda user_id, missing_id, db: notifications_service.create_follow_request_notification(
                missing_id, user_id, str(uuid.uuid4()), db
            ),
            lambda user_id, missing_id, db: notifications_service.create_follow_accepted_notification(
                missing_id, user_id, str(uuid.uuid4()), db
            ),
            lambda user_id, missing_id, db: notifications_service.create_admin_sign_up_approval_notification(
                missing_id, user_id, str(uuid.uuid4()), db
            ),
            lambda user_id, missing_id, db: notifications_service.create_admin_user_promoted_notification(
                missing_id, user_id, str(uuid.uuid4()), db
            ),
            lambda user_id, missing_id, db: notifications_service.create_idp_linked_notification(
                missing_id, uuid.uuid4(), str(uuid.uuid4()), db
            ),
            lambda user_id, missing_id, db: notifications_service.create_account_security_changed_notification(
                missing_id, "password_changed", None, str(uuid.uuid4()), db
            ),
            lambda user_id, missing_id, db: notifications_service.create_new_device_sign_in_notification(
                missing_id, "Firefox", "Linux", "10.0.0.1", str(uuid.uuid4()), db
            ),
        ],
        ids=["follow-request", "follow-accepted", "sign-up", "promotion", "idp-linked", "security", "new-device"],
    )
    def test_a_user_that_no_longer_exists_is_not_found_and_nothing_is_stored(self, db, create):
        user = make_user(db)

        with pytest.raises(core_exceptions.NotFoundError):
            create(user.id, uuid.uuid4(), db)

        assert _stored(db) == []

    def test_an_idp_link_records_the_provider_name_or_none_once_it_is_gone(self, db):
        user = make_user(db)
        idp_id = make_identity_provider(db, "keycloak")

        notifications_service.create_idp_linked_notification(user.id, idp_id, str(uuid.uuid4()), db)
        notifications_service.create_idp_linked_notification(user.id, uuid.uuid4(), str(uuid.uuid4()), db)

        names = {n.options["idp_name"] for n in _stored(db, user.id)}
        assert names == {"Provider keycloak", None}

    def test_a_security_change_records_only_the_extras_that_apply(self, db):
        user = make_user(db)
        idp_id = make_identity_provider(db, "okta")
        cases = {
            "password_changed": {},
            "identity_provider_unlinked": {"idp_id": idp_id},
            "role_changed_by_admin": {"access_type": "admin"},
            "backup_code_used": {"backup_codes_remaining": 3},
        }

        for change, extras in cases.items():
            notifications_service.create_account_security_changed_notification(
                user.id,
                change,
                extras.get("idp_id"),
                str(uuid.uuid4()),
                db,
                access_type=extras.get("access_type"),
                backup_codes_remaining=extras.get("backup_codes_remaining"),
            )

        recorded = {n.options["change"]: n.options for n in _stored(db, user.id)}
        assert recorded == {
            "password_changed": {"change": "password_changed"},
            "identity_provider_unlinked": {
                "change": "identity_provider_unlinked",
                "idp_id": str(idp_id),
                "idp_name": "Provider okta",
            },
            "role_changed_by_admin": {"change": "role_changed_by_admin", "access_type": "admin"},
            "backup_code_used": {"change": "backup_code_used", "backup_codes_remaining": 3},
        }

    def test_an_unlink_of_a_deleted_provider_leaves_the_name_empty(self, db):
        user = make_user(db)
        gone = uuid.uuid4()

        notifications_service.create_account_security_changed_notification(
            user.id, "identity_provider_unlinked", gone, str(uuid.uuid4()), db
        )

        assert self._options(db, user.id, _TYPES.ACCOUNT_SECURITY_CHANGED)["idp_name"] is None

    def test_a_new_device_sign_in_records_the_browser_the_system_and_the_address(self, db):
        user = make_user(db)

        notifications_service.create_new_device_sign_in_notification(
            user.id, "Firefox", "Linux", "10.0.0.1", str(uuid.uuid4()), db
        )

        assert self._options(db, user.id, _TYPES.NEW_DEVICE_SIGN_IN) == {
            "browser": "Firefox",
            "operating_system": "Linux",
            "ip_address": "10.0.0.1",
        }


class TestRemoveFollowRequestNotifications:
    def test_the_request_notifications_of_the_requester_are_removed_and_reported(self, db):
        requester, target, other = make_user(db), make_user(db), make_user(db)
        named = {"user_id": str(requester.id), "user_name": "n", "user_username": "u"}
        make_notification_of(db, target.id, _TYPES.NEW_FOLLOWER_REQUEST, named)
        kept = make_notification_of(db, target.id, _TYPES.NEW_FOLLOWER_REQUEST, {**named, "user_id": str(other.id)})

        assert notifications_service.remove_follow_request_notifications(requester.id, target.id, db) is True
        assert notifications_service.remove_follow_request_notifications(requester.id, target.id, db) is False
        assert [n.id for n in _stored(db)] == [kept.id]
