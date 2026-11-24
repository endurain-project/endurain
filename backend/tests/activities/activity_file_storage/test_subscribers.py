"""A deleted activity's retained source file is removed, on the in-process bus and by a durable worker."""

import uuid

import jasil.jobs.registry as jobs_registry
import pytest
from jasil.events import Event
from pydantic import ValidationError

import core.config as core_config
import modules.activities.activity.events as activity_events
import modules.activities.activity_file_storage.integration_service as file_storage
import modules.activities.activity_file_storage.subscribers as file_subscribers
from tests._factories.activities import make_activity
from tests._factories.garmin import activity_gpx
from tests._factories.ingestion import fit_file
from tests._factories.users import make_user

_API = core_config.ROOT_PATH


def _deleted_event(activity_id: object) -> Event:
    return Event(
        event_id=str(uuid.uuid4()),
        event_type=activity_events.ACTIVITY_DELETED,
        source="test",
        timestamp="2026-01-01T00:00:00+00:00",
        payload={"activity_id": str(activity_id)},
        retry_count=1,
        max_attempts=3,
    )


class TestOnTheBus:
    def test_deleting_an_activity_removes_its_retained_file(self, platform, storage, committed_sessions, sign_in):
        file_subscribers.register_bus_subscribers(platform.events)
        with committed_sessions() as db:
            user = make_user(db)
            activity = make_activity(db, user.id)
            db.commit()
        file_storage.store_activity_file(activity.id, ".fit", fit_file(), storage)
        other = uuid.uuid4()
        file_storage.store_activity_file(other, ".gpx", activity_gpx(), storage)
        me = sign_in(user)
        etag = me.client.get(f"{_API}/activities/{activity.id}").headers["ETag"]

        response = me.client.delete(f"{_API}/activities/{activity.id}", headers={"If-Match": etag})

        assert response.status_code == 204
        assert file_storage.get_activity_file(activity.id, storage) is None
        assert file_storage.get_activity_file(other, storage) is not None

    def test_a_storage_failure_never_breaks_the_deletion(
        self, platform, storage, committed_sessions, sign_in, break_storage
    ):
        file_subscribers.register_bus_subscribers(platform.events)
        with committed_sessions() as db:
            user = make_user(db)
            activity = make_activity(db, user.id)
            db.commit()
        file_storage.store_activity_file(activity.id, ".fit", fit_file(), storage)
        break_storage(delete=RuntimeError("storage is down"))
        me = sign_in(user)
        etag = me.client.get(f"{_API}/activities/{activity.id}").headers["ETag"]

        response = me.client.delete(f"{_API}/activities/{activity.id}", headers={"If-Match": etag})

        assert response.status_code == 204
        assert file_storage.get_activity_file(activity.id, storage) is not None, "the sweep removes it later"


class TestOnADurableWorker:
    @pytest.fixture
    def handler(self):
        registry = jobs_registry.JobHandlerRegistry()
        file_subscribers.register_durable_handlers(registry)
        assert registry.subscribers_for(activity_events.ACTIVITY_DELETED) == (
            file_subscribers.ACTIVITY_FILE_CLEANUP_SUBSCRIBER_ID,
        )
        return registry.get(file_subscribers.ACTIVITY_FILE_CLEANUP_SUBSCRIBER_ID)

    def test_removes_the_file_of_the_deleted_activity_and_no_other(self, handler, storage):
        gone, kept = uuid.uuid4(), uuid.uuid4()
        file_storage.store_activity_file(gone, ".fit", fit_file(), storage)
        file_storage.store_activity_file(kept, ".fit", fit_file(), storage)

        handler(_deleted_event(gone))

        assert file_storage.get_activity_file(gone, storage) is None
        assert file_storage.get_activity_file(kept, storage) is not None

    def test_an_activity_that_never_had_a_file_is_not_an_error(self, handler):
        handler(_deleted_event(uuid.uuid4()))

    def test_a_malformed_event_is_refused(self, handler):
        with pytest.raises(ValidationError):
            handler(_deleted_event("not-a-uuid"))

    def test_a_storage_failure_is_raised_so_the_runner_retries(self, handler, break_storage):
        break_storage(delete=RuntimeError("storage is down"))

        with pytest.raises(RuntimeError, match="storage is down"):
            handler(_deleted_event(uuid.uuid4()))
