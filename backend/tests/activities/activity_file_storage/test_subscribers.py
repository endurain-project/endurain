"""A deleted activity's retained source file is removed, on the in-process bus and by a durable worker."""

import uuid

import jasil.jobs.registry as jobs_registry
import pytest
from jasil.events import Event
from pydantic import ValidationError
from sqlalchemy import select, text

import core.config as core_config
import modules.activities.activity.events as activity_events
import modules.activities.activity_file_storage.constants as activity_file_storage_constants
import modules.activities.activity_file_storage.integration_service as file_storage
import modules.activities.activity_file_storage.models as file_models
import modules.activities.activity_file_storage.subscribers as file_subscribers
from tests._factories.activities import make_activity
from tests._factories.garmin import activity_gpx
from tests._factories.ingestion import fit_file, retain_file, store_legacy_file
from tests._factories.users import make_user

_API = core_config.ROOT_PATH
_AREA = activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA
_State = activity_file_storage_constants.ActivityFileState


def _deleted_event(activity_id: object, file_id: object = None) -> Event:
    payload = {"activity_id": str(activity_id)}
    if file_id is not None:
        payload["file_id"] = str(file_id)
    return Event(
        event_id=str(uuid.uuid4()),
        event_type=activity_events.ACTIVITY_DELETED,
        source="test",
        timestamp="2026-01-01T00:00:00+00:00",
        payload=payload,
        retry_count=1,
        max_attempts=3,
    )


def _state_of(committed_sessions, file_id) -> str | None:
    with committed_sessions() as db:
        return db.scalars(select(file_models.ActivityFile.state).where(file_models.ActivityFile.id == file_id)).first()


class TestOnTheBus:
    def test_deleting_an_activity_removes_its_retained_file_and_row(
        self, platform, storage, committed_sessions, sign_in
    ):
        file_subscribers.register_bus_subscribers(platform.events)
        with committed_sessions() as db:
            user = make_user(db)
            activity = make_activity(db, user.id)
            db.commit()
        file_id = retain_file(user.id, activity.id, fit_file(), storage)
        other = uuid.uuid4()
        store_legacy_file(other, activity_gpx(), storage, extension=".gpx")
        me = sign_in(user)
        etag = me.client.get(f"{_API}/activities/{activity.id}").headers["ETag"]

        response = me.client.delete(f"{_API}/activities/{activity.id}", headers={"If-Match": etag})

        assert response.status_code == 204
        assert storage.get(_AREA, f"files/{file_id}.fit") is None
        assert _state_of(committed_sessions, file_id) is None
        assert file_storage.read_file(other, None, storage) is not None

    def test_a_storage_failure_never_breaks_the_deletion(
        self, platform, storage, committed_sessions, sign_in, break_storage
    ):
        file_subscribers.register_bus_subscribers(platform.events)
        with committed_sessions() as db:
            user = make_user(db)
            activity = make_activity(db, user.id)
            db.commit()
        file_id = retain_file(user.id, activity.id, fit_file(), storage)
        break_storage(delete=RuntimeError("storage is down"))
        me = sign_in(user)
        etag = me.client.get(f"{_API}/activities/{activity.id}").headers["ETag"]

        response = me.client.delete(f"{_API}/activities/{activity.id}", headers={"If-Match": etag})

        assert response.status_code == 204
        assert _state_of(committed_sessions, file_id) == _State.DELETING, "the sweep finishes it later"


class TestOnADurableWorker:
    @pytest.fixture
    def handler(self):
        registry = jobs_registry.JobHandlerRegistry()
        file_subscribers.register_durable_handlers(registry)
        assert registry.subscribers_for(activity_events.ACTIVITY_DELETED) == (
            file_subscribers.ACTIVITY_FILE_CLEANUP_SUBSCRIBER_ID,
        )
        return registry.get(file_subscribers.ACTIVITY_FILE_CLEANUP_SUBSCRIBER_ID)

    @pytest.fixture
    def user(self, committed_sessions):
        with committed_sessions() as db:
            created = make_user(db)
            db.commit()
            return created

    def _deleted_activity_file(self, committed_sessions, user, storage, data=b"fit-bytes"):
        """Retain a file for an activity, then delete the activity as the delete route does."""
        with committed_sessions() as db:
            activity = make_activity(db, user.id)
            db.commit()
        file_id = retain_file(user.id, activity.id, data, storage)
        with committed_sessions() as db:
            db.execute(text("DELETE FROM activities WHERE id = :id"), {"id": activity.id})
            db.commit()
        return activity.id, file_id

    def test_removes_the_file_of_the_deleted_activity_and_no_other(self, handler, storage, committed_sessions, user):
        gone_activity, gone_file = self._deleted_activity_file(committed_sessions, user, storage, b"one")
        with committed_sessions() as db:
            kept_activity = make_activity(db, user.id)
            db.commit()
        kept_file = retain_file(user.id, kept_activity.id, b"two", storage)

        handler(_deleted_event(gone_activity, gone_file))

        assert storage.get(_AREA, f"files/{gone_file}.fit") is None
        assert _state_of(committed_sessions, gone_file) is None
        assert storage.get(_AREA, f"files/{kept_file}.fit") == b"two"

    def test_keeps_a_file_another_activity_still_references(self, handler, storage, committed_sessions, user):
        with committed_sessions() as db:
            first = make_activity(db, user.id)
            second = make_activity(db, user.id)
            db.commit()
        shared = retain_file(user.id, first.id, b"shared", storage)
        with committed_sessions() as db:
            db.execute(text("UPDATE activities SET file_id = :file WHERE id = :id"), {"file": shared, "id": second.id})
            db.execute(text("DELETE FROM activities WHERE id = :id"), {"id": first.id})
            db.commit()

        handler(_deleted_event(first.id, shared))

        assert storage.get(_AREA, f"files/{shared}.fit") == b"shared"
        assert _state_of(committed_sessions, shared) == _State.ATTACHED

    def test_a_retry_after_a_storage_failure_finishes_the_removal(
        self, handler, storage, committed_sessions, user, break_storage
    ):
        activity_id, file_id = self._deleted_activity_file(committed_sessions, user, storage)
        break_storage(delete=RuntimeError("storage is down"))
        with pytest.raises(RuntimeError, match="storage is down"):
            handler(_deleted_event(activity_id, file_id))
        assert _state_of(committed_sessions, file_id) == _State.DELETING

        break_storage()
        handler(_deleted_event(activity_id, file_id))

        assert storage.get(_AREA, f"files/{file_id}.fit") is None
        assert _state_of(committed_sessions, file_id) is None

    def test_an_event_for_a_row_that_is_gone_is_a_no_op(self, handler):
        handler(_deleted_event(uuid.uuid4(), uuid.uuid4()))

    def test_an_activity_without_a_file_row_has_its_legacy_file_deleted_by_id(self, handler, storage):
        gone, kept = uuid.uuid4(), uuid.uuid4()
        store_legacy_file(gone, fit_file(), storage)
        store_legacy_file(kept, fit_file(), storage)

        handler(_deleted_event(gone))

        assert file_storage.read_file(gone, None, storage) is None
        assert file_storage.read_file(kept, None, storage) is not None

    def test_an_activity_that_never_had_a_file_is_not_an_error(self, handler):
        handler(_deleted_event(uuid.uuid4()))

    def test_a_malformed_event_is_refused(self, handler):
        with pytest.raises(ValidationError):
            handler(_deleted_event("not-a-uuid"))

    def test_a_storage_failure_on_a_legacy_delete_is_raised_so_the_runner_retries(self, handler, break_storage):
        break_storage(delete=RuntimeError("storage is down"))

        with pytest.raises(RuntimeError, match="storage is down"):
            handler(_deleted_event(uuid.uuid4()))
