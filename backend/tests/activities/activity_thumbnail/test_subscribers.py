"""Thumbnails follow their activity's life: created, deleted, and a changed tile source, through the bus."""

import uuid

import jasil.runtime as platform_runtime
import pydantic
import pytest
from jasil.events import new_event
from jasil.jobs.registry import JobHandlerRegistry

import core.config as core_config
import core.exceptions as core_exceptions
import core.scheduler as core_scheduler
import modules.activities.activity.events as activity_events
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
import modules.activities.activity_streams.constants as stream_constants
import modules.activities.activity_thumbnail.constants as thumbnail_constants
import modules.activities.activity_thumbnail.subscriber_registry as thumbnail_subscriber_registry
import modules.activities.activity_thumbnail.subscribers as thumbnail_subscribers
import modules.server_settings.events as server_settings_events
from tests._factories.activities import make_activity, make_stream
from tests._factories.server_settings import edit_server_settings
from tests._factories.users import make_user

_AREA = thumbnail_constants.THUMBNAIL_STORAGE_AREA
_MAP = stream_constants.STREAM_TYPE_MAP
_ROUTE = [{"lat": 38.70, "lon": -9.10}, {"lat": 38.72, "lon": -9.14}]


@pytest.fixture
def storage():
    return platform_runtime.get_active_platform().storage


@pytest.fixture
def events():
    return platform_runtime.get_active_platform().events


def _created(activity_id: uuid.UUID, user_id: uuid.UUID):
    payload = activity_events.ActivityCreatedPayload(activity_id=activity_id, user_id=user_id)
    return new_event(activity_events.ACTIVITY_CREATED, payload.model_dump(mode="json"), source="test")


def _deleted(activity_id: uuid.UUID):
    return new_event(activity_events.ACTIVITY_DELETED, {"activity_id": str(activity_id)}, source="test")


def _tiles_changed(*, regenerate: bool):
    payload = {"changed_fields": ["tileserver_url"], "regenerate_thumbnails": regenerate}
    return new_event(server_settings_events.TILE_SETTINGS_CHANGED, payload, source="test")


@pytest.fixture
def routed(db, tile_server):
    edit_server_settings(db, tileserver_url=tile_server.url())
    user = make_user(db)
    activity = make_activity(db, user.id)
    make_stream(db, activity, _MAP, _ROUTE)
    return user, activity


def _key_of(db, activity) -> str | None:
    db.expire_all()
    return db.get(activity_models.Activity, activity.id).map_thumbnail_path


class TestCreated:
    def test_a_created_activity_with_a_route_gets_its_thumbnail_through_the_bus(self, db, events, storage, routed):
        user, activity = routed
        thumbnail_subscribers.register_bus_subscribers(events)

        events.publish(_created(activity.id, user.id))

        assert _key_of(db, activity) == f"{activity.id}.webp"
        assert storage.exists(_AREA, f"{activity.id}.webp")

    def test_an_activity_without_a_route_gets_none(self, db, events, storage, tile_server):
        user = make_user(db)
        activity = make_activity(db, user.id)
        thumbnail_subscribers.register_bus_subscribers(events)

        events.publish(_created(activity.id, user.id))

        assert (_key_of(db, activity), list(storage.list_keys(_AREA, ""))) == (None, [])

    def test_a_tile_server_failure_is_raised_to_the_durable_runner_and_swallowed_on_the_bus(
        self, db, storage, routed, tile_server
    ):
        user, activity = routed
        tile_server.status = 500

        with pytest.raises(core_exceptions.ProcessingError):
            thumbnail_subscribers.generate_activity_thumbnail_for_event(_created(activity.id, user.id))
        thumbnail_subscribers.on_activity_created_generate_thumbnail(_created(activity.id, user.id))

        assert _key_of(db, activity) is None

    def test_an_event_without_an_owner_is_refused_so_the_runner_retries(self):
        event = new_event(activity_events.ACTIVITY_CREATED, {"activity_id": str(uuid.uuid4())}, source="test")

        with pytest.raises(pydantic.ValidationError):
            thumbnail_subscribers.generate_activity_thumbnail_for_event(event)


class TestDeleted:
    def test_deleting_an_activity_over_http_removes_its_thumbnail(
        self, events, sign_in, people, make_owned_activity, storage
    ):
        activity = make_owned_activity()
        storage.save(_AREA, f"{activity.id}.webp", b"webp")
        thumbnail_subscribers.register_bus_subscribers(events)

        response = sign_in(people.owner).client.delete(
            f"{core_config.ROOT_PATH}/activities/{activity.id}", headers={"If-Match": '"1"'}
        )

        assert response.status_code == 204
        assert not storage.exists(_AREA, f"{activity.id}.webp")

    def test_only_the_deleted_activitys_thumbnail_goes_and_a_repeat_is_harmless(self, events, storage):
        gone, kept = uuid.uuid4(), uuid.uuid4()
        for activity_id in (gone, kept):
            storage.save(_AREA, f"{activity_id}.webp", b"webp")
        thumbnail_subscribers.register_bus_subscribers(events)

        events.publish(_deleted(gone))
        events.publish(_deleted(gone))

        assert list(storage.list_keys(_AREA, "")) == [f"{kept}.webp"]


class TestTileSettingsChanged:
    def test_a_change_that_asks_for_regeneration_renders_every_thumbnail_again(
        self, db, events, storage, routed, tile_server
    ):
        _, activity = routed
        storage.save(_AREA, f"{activity.id}.webp", b"stale")
        activity_integration.set_thumbnail_key(activity.id, f"{activity.id}.webp", db)
        thumbnail_subscribers.register_bus_subscribers(events)

        events.publish(_tiles_changed(regenerate=True))

        assert storage.get(_AREA, f"{activity.id}.webp") != b"stale"
        assert tile_server.requests

    async def test_with_a_scheduler_in_the_process_the_pass_is_queued_on_it_instead_of_run_inline(
        self, db, events, storage, routed, tile_server
    ):
        _, activity = routed
        storage.save(_AREA, f"{activity.id}.webp", b"stale")
        thumbnail_subscribers.register_bus_subscribers(events)
        job_id = "endurain_regenerate_all_thumbnails"
        core_scheduler.scheduler.start(paused=True)
        try:
            events.publish(_tiles_changed(regenerate=True))

            assert core_scheduler.scheduler.get_job(job_id) is not None
            assert (storage.get(_AREA, f"{activity.id}.webp"), tile_server.requests) == (b"stale", [])
        finally:
            core_scheduler.scheduler.remove_all_jobs()
            core_scheduler.scheduler.shutdown(wait=False)

    def test_a_change_that_does_not_ask_for_it_leaves_the_thumbnails_alone(
        self, db, events, storage, routed, tile_server
    ):
        _, activity = routed
        storage.save(_AREA, f"{activity.id}.webp", b"stale")
        thumbnail_subscribers.register_bus_subscribers(events)

        events.publish(_tiles_changed(regenerate=False))

        assert (storage.get(_AREA, f"{activity.id}.webp"), tile_server.requests) == (b"stale", [])


class TestRegistry:
    def test_the_package_registers_its_bus_subscribers_and_durable_handlers_under_stable_ids(self):
        registry = JobHandlerRegistry()

        thumbnail_subscriber_registry.register_durable_handlers(registry)

        assert registry.subscribers_for(activity_events.ACTIVITY_CREATED) == ("activity_thumbnail.generate",)
        assert registry.subscribers_for(activity_events.ACTIVITY_DELETED) == ("activity_thumbnail.cleanup",)
        assert registry.subscribers_for(server_settings_events.TILE_SETTINGS_CHANGED) == (
            "activity_thumbnail.settings_changed",
        )

    def test_the_package_wires_the_bus_through_its_registry(self, events, storage):
        activity_id = uuid.uuid4()
        storage.save(_AREA, f"{activity_id}.webp", b"webp")

        thumbnail_subscriber_registry.register_bus_subscribers(events)
        events.publish(_deleted(activity_id))

        assert list(storage.list_keys(_AREA, "")) == []
