"""Tests for installed module runtime composition."""

from unittest.mock import MagicMock

from jasil.jobs.registry import JobHandlerRegistry

import module_registry as runtime_module_registry
import modules.activities.activity.events as activity_events
import modules.activities.activity_ingestion.events as ingestion_events
import modules.activities.contributor_registry as activity_contributor_registry

_EXPECTED_CREATED_SUBSCRIBERS = {
    "activity_thumbnail.generate",
    "activity.notify_created",
    "activity_streams.compute_hr_zones",
    "activity_geocoding.reverse_geocode",
}
_EXPECTED_DELETED_SUBSCRIBERS = {
    "activity_thumbnail.cleanup",
    "activity_file_storage.cleanup",
    "activity_media.cleanup",
}


def _register_durable_handlers() -> JobHandlerRegistry:
    registry = JobHandlerRegistry()
    runtime_module_registry.register_durable_handlers(registry)
    return registry


class TestRuntimeModuleRegistry:
    def test_configures_all_installed_activity_contributors_idempotently(self):
        runtime_module_registry.configure_activity_contributors()
        runtime_module_registry.configure_activity_contributors()

        assert {item.key for item in activity_contributor_registry.activity_ingestion_contributors()} == {
            "laps",
            "sets",
            "streams",
            "workout_steps",
        }
        assert {item.key for item in activity_contributor_registry.file_ingestion_contributors()} == {"exercise_titles"}
        assert {item.key for item in activity_contributor_registry.profile_activity_contributors()} == {
            "laps",
            "sets",
            "streams",
            "workout_steps",
            "media",
        }
        assert {item.key for item in activity_contributor_registry.profile_global_contributors()} == {"exercise_titles"}

    def test_installs_the_thumbnail_url_resolver(self):
        """Without it every serialized activity silently loses its thumbnail URL.

        The root activity package asks the registry rather than importing the
        thumbnail package, so a missing registration is not an import error — it
        is a null URL on every activity in the API.
        """
        activity_contributor_registry.clear()
        assert activity_contributor_registry.resolve_thumbnail_url("42.webp", 42) is None

        runtime_module_registry.configure_activity_contributors()

        assert activity_contributor_registry.resolve_thumbnail_url("42.webp", 42) is not None
        assert activity_contributor_registry.resolve_thumbnail_url(None, 42) is None

    def test_registers_every_activity_bus_subscriber(self):
        events = MagicMock()
        runtime_module_registry.register_bus_subscribers(events)
        event_types = [call.args[0] for call in events.subscribe.call_args_list]
        assert event_types.count(activity_events.ACTIVITY_CREATED) == 4
        assert event_types.count(activity_events.ACTIVITY_DELETED) == 3

    def test_registers_every_activity_durable_handler(self):
        registry = _register_durable_handlers()
        assert set(registry.subscribers_for(activity_events.ACTIVITY_CREATED)) == _EXPECTED_CREATED_SUBSCRIBERS
        assert set(registry.subscribers_for(activity_events.ACTIVITY_DELETED)) == _EXPECTED_DELETED_SUBSCRIBERS
        assert set(registry.subscribers_for(ingestion_events.ACTIVITY_BULK_IMPORT_FILE)) == {
            "activity_ingestion.bulk_import_file"
        }
        assert set(registry.subscribers_for(ingestion_events.ACTIVITY_FILE_UPLOADED)) == {
            "activity_ingestion.uploaded_file"
        }
        assert set(registry.subscribers_for(ingestion_events.ACTIVITY_REFRESH_REQUESTED)) == {
            "activity_ingestion.refresh_requested"
        }

    def test_profile_restore_reactions_are_declared(self):
        registry = _register_durable_handlers()
        nets = {net.subscriber_id: net for module in runtime_module_registry.MODULES for net in module.nets}
        healed: set[str] = set()
        exempt: set[str] = set()
        for subscriber_id in registry.subscribers_for(activity_events.ACTIVITY_CREATED):
            net = nets[subscriber_id]
            if net.backfill is not None:
                healed.add(subscriber_id)
            else:
                assert net.exempt_reason
                exempt.add(subscriber_id)
        assert healed == {
            "activity_thumbnail.generate",
            "activity_streams.compute_hr_zones",
            "activity_geocoding.reverse_geocode",
        }
        assert exempt == {"activity.notify_created"}

    def test_all_registered_handlers_resolve(self):
        registry = _register_durable_handlers()
        for subscriber_id in registry.subscriber_ids():
            assert registry.get(subscriber_id) is not None
