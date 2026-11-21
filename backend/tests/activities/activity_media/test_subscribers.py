"""Media blobs follow their activity: deleting it removes them through the bus and the durable handler."""

import dataclasses
import uuid

import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
import pydantic
import pytest
from jasil.backends.storage_local import LocalStorage
from jasil.events import new_event
from jasil.jobs.registry import JobHandlerRegistry

import core.config as core_config
import modules.activities.activity.events as activity_events
import modules.activities.activity_media.constants as media_constants
import modules.activities.activity_media.subscriber_registry as media_subscriber_registry
import modules.activities.activity_media.subscribers as media_subscribers
from tests._factories.activities import make_stored_media
from tests._helpers import images

_AREA = media_constants.MEDIA_STORAGE_AREA


class UnavailableStorage(LocalStorage):
    """Local storage that cannot list, as an object store that is down cannot."""

    def list_keys(self, area: str, prefix: str):
        raise platform_providers.StorageBackendUnavailableError("storage down")


@pytest.fixture
def storage():
    return platform_runtime.get_active_platform().storage


@pytest.fixture
def subscribed():
    media_subscribers.register_bus_subscribers(platform_runtime.get_active_platform().events)


def _deleted(activity_id: uuid.UUID):
    return new_event(activity_events.ACTIVITY_DELETED, {"activity_id": str(activity_id)}, source="test")


def _stage_photo(db, activity):
    make_stored_media(db, activity, images.png_with_text(), "a.png")


class TestOnTheBus:
    def test_deleting_an_activity_over_http_removes_its_blobs(
        self, subscribed, sign_in, people, make_owned_activity, storage
    ):
        activity = make_owned_activity(stage=_stage_photo)
        assert len(list(storage.list_keys(_AREA, f"{activity.id}_"))) == 1

        response = sign_in(people.owner).client.delete(
            f"{core_config.ROOT_PATH}/activities/{activity.id}", headers={"If-Match": '"1"'}
        )

        assert response.status_code == 204
        assert list(storage.list_keys(_AREA, f"{activity.id}_")) == []

    def test_only_the_deleted_activitys_blobs_go(self, subscribed, make_owned_activity, storage):
        gone = make_owned_activity(stage=_stage_photo)
        kept = make_owned_activity(
            stage=_stage_photo, start_time=gone.start_time.replace(day=12), end_time=gone.end_time.replace(day=12)
        )

        platform_runtime.get_active_platform().events.publish(_deleted(gone.id))

        assert list(storage.list_keys(_AREA, f"{gone.id}_")) == []
        assert len(list(storage.list_keys(_AREA, f"{kept.id}_"))) == 1

    def test_a_storage_failure_never_reaches_the_publisher_and_the_blob_stays(self, make_owned_activity, tmp_path):
        activity = make_owned_activity(stage=_stage_photo)
        platform = platform_runtime.get_active_platform()
        down = UnavailableStorage(str(tmp_path / "down"), plain_areas=frozenset({_AREA}))
        platform_runtime.set_active_platform(dataclasses.replace(platform, storage=down))

        media_subscribers.on_activity_deleted_cleanup_media(_deleted(activity.id))

        assert len(list(platform.storage.list_keys(_AREA, f"{activity.id}_"))) == 1


class TestRegistry:
    def test_the_package_registers_its_bus_subscriber_and_its_durable_handler_with_a_sweep_net(
        self, make_owned_activity, storage
    ):
        activity = make_owned_activity(stage=_stage_photo)
        registry = JobHandlerRegistry()

        media_subscriber_registry.register_bus_subscribers(platform_runtime.get_active_platform().events)
        media_subscriber_registry.register_durable_handlers(registry)
        platform_runtime.get_active_platform().events.publish(_deleted(activity.id))

        assert list(storage.list_keys(_AREA, f"{activity.id}_")) == []
        assert registry.subscribers_for(activity_events.ACTIVITY_DELETED) == ("activity_media.cleanup",)
        [net] = media_subscriber_registry.DURABLE_SUBSCRIBER_NETS
        assert net.subscriber_id == "activity_media.cleanup"


class TestDurableHandler:
    def test_the_handler_removes_the_blobs_of_the_activity_named_in_the_event(self, make_owned_activity, storage):
        activity = make_owned_activity(stage=_stage_photo)

        media_subscribers.cleanup_activity_media_for_event(_deleted(activity.id))

        assert list(storage.list_keys(_AREA, f"{activity.id}_")) == []

    def test_an_event_without_an_activity_id_is_refused_so_the_runner_retries(self):
        event = new_event(activity_events.ACTIVITY_DELETED, {}, source="test")

        with pytest.raises(pydantic.ValidationError):
            media_subscribers.cleanup_activity_media_for_event(event)

    def test_the_handler_is_registered_for_activity_deleted_under_its_stable_id(self):
        registry = JobHandlerRegistry()

        media_subscribers.register_durable_handlers(registry)

        assert registry.subscribers_for(activity_events.ACTIVITY_DELETED) == ("activity_media.cleanup",)
        assert registry.get("activity_media.cleanup") is media_subscribers.cleanup_activity_media_for_event
