"""Notification crud on the real database: reads, keyset slices, idempotent creation, marks and deletes."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.notifications.constants as notifications_constants
import modules.notifications.crud as notifications_crud
import modules.notifications.models as notifications_models
import modules.notifications.schema as notifications_schema
from tests._factories.notifications import make_notification, make_notification_of
from tests._factories.users import make_user

_NEW_ACTIVITY = notifications_constants.NotificationType.NEW_ACTIVITY
_FOLLOW_REQUEST = notifications_constants.NotificationType.NEW_FOLLOWER_REQUEST
_T0 = datetime(2024, 1, 1, tzinfo=UTC)


def _activity(db, user_id, **kwargs):
    return make_notification_of(db, user_id, _NEW_ACTIVITY, {"activity_id": str(uuid.uuid4())}, **kwargs)


def _naming(user):
    return {"user_id": str(user.id), "user_name": user.name, "user_username": user.username}


def _stored_ids(db) -> set[uuid.UUID]:
    return set(db.scalars(select(notifications_models.Notification.id)))


class TestReads:
    def test_a_notification_is_read_back_by_its_owner_only(self, db):
        owner, other = make_user(db), make_user(db)
        notification = make_notification(db, owner.id)

        assert notifications_crud.get_user_notification_by_id(notification.id, owner.id, db) == notification
        assert notifications_crud.get_user_notification_by_id(notification.id, other.id, db) is None
        assert notifications_crud.get_user_notification_by_id(uuid.uuid4(), owner.id, db) is None

    def test_the_unread_count_skips_read_and_other_users_notifications(self, db):
        user, other = make_user(db), make_user(db)
        _activity(db, user.id)
        _activity(db, user.id)
        _activity(db, user.id, read=True)
        _activity(db, other.id)

        assert notifications_crud.count_user_unread_notifications(user.id, db) == 2

    def test_the_unread_count_is_zero_for_a_user_without_notifications(self, db):
        assert notifications_crud.count_user_unread_notifications(make_user(db).id, db) == 0


class TestKeysetSlice:
    @pytest.fixture
    def feed(self, db):
        """A user with five notifications, oldest first (the second and fourth read), and another user's one."""
        user, other = make_user(db), make_user(db)
        rows = [
            _activity(db, user.id, read=index in (1, 3), created_at=_T0 + timedelta(days=index)) for index in range(5)
        ]
        _activity(db, other.id, created_at=_T0 + timedelta(days=9))
        return user, rows

    def test_the_slice_is_newest_first_and_holds_only_the_users_rows(self, db, feed):
        user, rows = feed

        page = notifications_crud.get_user_notifications_after(user.id, None, 10, db)

        assert [n.id for n in page] == [n.id for n in reversed(rows)]

    def test_the_slice_is_cut_at_the_requested_size(self, db, feed):
        user, rows = feed

        page = notifications_crud.get_user_notifications_after(user.id, None, 2, db)

        assert [n.id for n in page] == [rows[4].id, rows[3].id]

    def test_unread_only_keeps_the_unread_rows(self, db, feed):
        user, rows = feed

        page = notifications_crud.get_user_notifications_after(user.id, None, 10, db, unread_only=True)

        assert [n.id for n in page] == [rows[4].id, rows[2].id, rows[0].id]
        assert all(not n.read for n in page)

    def test_the_slice_resumes_strictly_after_the_position(self, db, feed):
        user, rows = feed

        page = notifications_crud.get_user_notifications_after(
            user.id, (rows[3].created_at, rows[3].id), 10, db, unread_only=True
        )

        assert [n.id for n in page] == [rows[2].id, rows[0].id]

    def test_notifications_sharing_a_creation_time_are_ordered_and_resumed_by_id(self, db):
        user = make_user(db)
        tied = [_activity(db, user.id, created_at=_T0) for _ in range(3)]
        by_id = sorted(tied, key=lambda n: n.id, reverse=True)

        first = notifications_crud.get_user_notifications_after(user.id, None, 2, db)
        rest = notifications_crud.get_user_notifications_after(user.id, (_T0, first[-1].id), 10, db)

        assert [n.id for n in first] == [n.id for n in by_id[:2]]
        assert [n.id for n in rest] == [by_id[2].id]

    def test_a_user_without_notifications_gets_an_empty_slice(self, db):
        assert notifications_crud.get_user_notifications_after(make_user(db).id, None, 10, db) == []


class TestCreate:
    def test_a_notification_is_stored_unread_with_its_options(self, db):
        user = make_user(db)

        created = notifications_crud.create_notification(
            notifications_schema.NotificationCreate(
                type=_FOLLOW_REQUEST, user_id=user.id, options=_naming(make_user(db))
            ),
            db,
        )

        row = db.get(notifications_models.Notification, created.id)
        assert row is not None
        assert (row.user_id, row.type, row.read, row.source_event_id) == (user.id, _FOLLOW_REQUEST.stored, False, None)
        assert row.options == created.options.model_dump(mode="json")

    def test_a_notification_for_a_missing_user_is_refused(self, db):
        with pytest.raises(IntegrityError, match="notifications_user_id_fkey"):
            make_notification(db, uuid.uuid4())


class TestCreateOnce:
    @staticmethod
    def _create(db, user_id, event_id, activity_id=None):
        return notifications_crud.create_notification_once(
            notifications_schema.NotificationCreate(
                type=_NEW_ACTIVITY,
                user_id=user_id,
                source_event_id=event_id,
                options={"activity_id": str(activity_id or uuid.uuid4())},
            ),
            db,
        )

    def test_the_first_delivery_creates_and_a_replay_returns_the_stored_one(self, db):
        user = make_user(db)
        event_id = str(uuid.uuid4())

        first, created = self._create(db, user.id, event_id)
        replay, replay_created = self._create(db, user.id, event_id)

        assert (created, replay_created) == (True, False)
        assert replay.id == first.id
        assert len(_stored_ids(db)) == 1

    def test_the_same_event_notifies_another_user_or_type_separately(self, db):
        user, other = make_user(db), make_user(db)
        event_id = str(uuid.uuid4())

        _, for_user = self._create(db, user.id, event_id)
        _, for_other = self._create(db, other.id, event_id)
        _, other_type = notifications_crud.create_notification_once(
            notifications_schema.NotificationCreate(
                type=notifications_constants.NotificationType.GARMIN_TOKEN_EXPIRED,
                user_id=user.id,
                source_event_id=event_id,
                options={},
            ),
            db,
        )

        assert (for_user, for_other, other_type) == (True, True, True)
        assert len(_stored_ids(db)) == 3

    def test_a_notification_without_a_source_event_is_always_created(self, db):
        user = make_user(db)
        create = notifications_schema.NotificationCreate(
            type=notifications_constants.NotificationType.GARMIN_TOKEN_EXPIRED, user_id=user.id
        )

        _, first = notifications_crud.create_notification_once(create, db)
        _, second = notifications_crud.create_notification_once(create, db)

        assert (first, second) == (True, True)
        assert len(_stored_ids(db)) == 2

    def test_a_missing_user_is_not_found_and_leaves_the_session_usable(self, db):
        user = make_user(db)
        kept = make_notification(db, user.id)

        with pytest.raises(core_exceptions.NotFoundError):
            self._create(db, uuid.uuid4(), str(uuid.uuid4()))

        assert _stored_ids(db) == {kept.id}


class TestMarkAsRead:
    def test_the_users_notification_is_marked_read(self, db):
        user = make_user(db)
        notification = make_notification(db, user.id)

        marked = notifications_crud.mark_notification_as_read(notification.id, user.id, db)

        assert marked is not None and marked.read is True
        assert db.get(notifications_models.Notification, notification.id).read is True

    def test_another_users_or_a_missing_notification_is_not_marked(self, db):
        owner, other = make_user(db), make_user(db)
        notification = make_notification(db, owner.id)

        assert notifications_crud.mark_notification_as_read(notification.id, other.id, db) is None
        assert notifications_crud.mark_notification_as_read(uuid.uuid4(), owner.id, db) is None
        assert db.get(notifications_models.Notification, notification.id).read is False

    def test_several_are_marked_and_ids_that_are_not_the_users_are_skipped(self, db):
        user, other = make_user(db), make_user(db)
        mine = [_activity(db, user.id) for _ in range(3)]
        theirs = _activity(db, other.id)

        notifications_crud.mark_notifications_as_read([mine[0].id, theirs.id, uuid.uuid4()], user.id, db)

        read = set(
            db.scalars(select(notifications_models.Notification.id).where(notifications_models.Notification.read))
        )
        assert read == {mine[0].id}

    def test_marking_all_reads_every_unread_notification_of_the_user_only(self, db):
        user, other = make_user(db), make_user(db)
        mine = [_activity(db, user.id) for _ in range(2)]
        theirs = _activity(db, other.id)

        notifications_crud.mark_all_notifications_as_read(user.id, db)

        assert notifications_crud.count_user_unread_notifications(user.id, db) == 0
        assert notifications_crud.get_user_notification_by_id(theirs.id, other.id, db).read is False
        assert all(notifications_crud.get_user_notification_by_id(n.id, user.id, db).read for n in mine)


class TestDelete:
    def test_a_user_deletes_only_their_own_notification(self, db):
        user, other = make_user(db), make_user(db)
        mine, theirs = _activity(db, user.id), _activity(db, other.id)

        assert notifications_crud.delete_user_notification(theirs.id, user.id, db) is False
        assert notifications_crud.delete_user_notification(uuid.uuid4(), user.id, db) is False
        assert notifications_crud.delete_user_notification(mine.id, user.id, db) is True

        assert _stored_ids(db) == {theirs.id}

    def test_the_notifications_of_one_type_naming_a_user_are_deleted_for_one_owner(self, db):
        owner, other_owner, named, another = (make_user(db) for _ in range(4))
        gone = make_notification_of(db, owner.id, _FOLLOW_REQUEST, _naming(named))
        kept = [
            make_notification_of(db, other_owner.id, _FOLLOW_REQUEST, _naming(named)),
            make_notification_of(db, owner.id, _FOLLOW_REQUEST, _naming(another)),
            make_notification_of(
                db, owner.id, notifications_constants.NotificationType.NEW_FOLLOWER_REQUEST_ACCEPTED, _naming(named)
            ),
        ]

        deleted = notifications_crud.delete_user_reference_notifications(owner.id, _FOLLOW_REQUEST, named.id, db)

        assert deleted == 1
        assert _stored_ids(db) == {n.id for n in kept}
        assert gone.id not in _stored_ids(db)

    def test_every_owners_notification_naming_a_user_is_deleted(self, db):
        first, second, named, another = (make_user(db) for _ in range(4))
        make_notification_of(db, first.id, _FOLLOW_REQUEST, _naming(named))
        make_notification_of(
            db,
            second.id,
            notifications_constants.NotificationType.ADMIN_NEW_SIGN_UP_APPROVAL_REQUEST,
            _naming(named),
        )
        kept = [
            make_notification_of(db, first.id, _FOLLOW_REQUEST, _naming(another)),
            _activity(db, first.id),
            make_notification(db, second.id),
        ]

        deleted = notifications_crud.delete_notifications_naming_user(named.id, db)

        assert deleted == 2
        assert _stored_ids(db) == {n.id for n in kept}

    def test_read_notifications_before_the_cutoff_are_deleted_up_to_the_limit(self, db):
        user = make_user(db)
        cutoff = _T0 + timedelta(days=10)
        old_read = [_activity(db, user.id, read=True, created_at=_T0 + timedelta(days=d)) for d in range(3)]
        kept = [
            _activity(db, user.id, read=False, created_at=_T0),
            _activity(db, user.id, read=True, created_at=cutoff + timedelta(days=1)),
        ]

        first = notifications_crud.delete_read_notifications_before(cutoff, 2, db)
        second = notifications_crud.delete_read_notifications_before(cutoff, 2, db)

        assert (first, second) == (2, 1)
        assert _stored_ids(db) == {n.id for n in kept}
        assert not {n.id for n in old_read} & _stored_ids(db)
