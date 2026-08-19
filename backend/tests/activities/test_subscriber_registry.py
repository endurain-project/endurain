"""Tests for the shared activities subscriber-registration surface.

Covers the single registration surface used by both the API lifespan and the
standalone worker, plus the reconciliation-net invariant: every durable
subscriber is declared with either a scheduled backfill or a documented
exemption, and every declared backfill is actually scheduled — so a direct
``create_activity`` that publishes no event (e.g. the profile bulk-restore) is
healed instead of silently losing derived work.
"""

from unittest.mock import MagicMock

import modules.activities.activity.events as activity_events
import modules.activities.activity_ingestion.events as ingestion_events
import modules.activities.subscriber_registry as activity_subscriber_registry
from infra.jobs.registry import JobHandlerRegistry

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
_EXPECTED_BULK_IMPORT_SUBSCRIBERS = {"activity_ingestion.bulk_import_file"}
_EXPECTED_UPLOAD_SUBSCRIBERS = {"activity_ingestion.uploaded_file"}
_EXPECTED_REFRESH_SUBSCRIBERS = {"activity_ingestion.refresh_requested"}


def _register_durable_handlers() -> JobHandlerRegistry:
    registry = JobHandlerRegistry()
    activity_subscriber_registry.register_all_activity_durable_handlers(registry)
    return registry


def _registered_durable_ids(registry: JobHandlerRegistry) -> set[str]:
    ids: set[str] = set()
    for event_type in (
        activity_events.ACTIVITY_CREATED,
        activity_events.ACTIVITY_DELETED,
        ingestion_events.ACTIVITY_BULK_IMPORT_FILE,
        ingestion_events.ACTIVITY_FILE_UPLOADED,
        ingestion_events.ACTIVITY_REFRESH_REQUESTED,
    ):
        ids.update(registry.subscribers_for(event_type))
    return ids


class TestRegisterAllActivityBusSubscribers:
    def test_subscribes_every_activity_handler(self):
        events = MagicMock()
        activity_subscriber_registry.register_all_activity_bus_subscribers(events)
        subscribed_event_types = [c.args[0] for c in events.subscribe.call_args_list]
        # thumbnail(generate), notify, hr-zones, geocoding react to created;
        # thumbnail(cleanup) and source-file(cleanup) react to deleted.
        assert subscribed_event_types.count(activity_events.ACTIVITY_CREATED) == 4
        assert subscribed_event_types.count(activity_events.ACTIVITY_DELETED) == 3


class TestRegisterAllActivityDurableHandlers:
    def test_registers_every_durable_subscriber(self):
        registry = _register_durable_handlers()
        assert set(registry.subscribers_for(activity_events.ACTIVITY_CREATED)) == _EXPECTED_CREATED_SUBSCRIBERS
        assert set(registry.subscribers_for(activity_events.ACTIVITY_DELETED)) == _EXPECTED_DELETED_SUBSCRIBERS
        assert (
            set(registry.subscribers_for(ingestion_events.ACTIVITY_BULK_IMPORT_FILE))
            == _EXPECTED_BULK_IMPORT_SUBSCRIBERS
        )
        assert set(registry.subscribers_for(ingestion_events.ACTIVITY_FILE_UPLOADED)) == _EXPECTED_UPLOAD_SUBSCRIBERS
        assert (
            set(registry.subscribers_for(ingestion_events.ACTIVITY_REFRESH_REQUESTED)) == _EXPECTED_REFRESH_SUBSCRIBERS
        )

    def test_every_handler_resolves(self):
        registry = _register_durable_handlers()
        for subscriber_id in _registered_durable_ids(registry):
            assert registry.get(subscriber_id) is not None


class TestReconciliationNetInvariant:
    def test_profile_restore_direct_create_is_healed(self):
        # A profile bulk-restore persists via create_activity directly and publishes
        # NO activity.created, relying entirely on the reconciliation nets. Every
        # durable subscriber that reacts to activity.created must therefore be healed
        # by a scheduled backfill, or be an explicitly-justified transient exemption
        # (the notification subscriber) — otherwise restored activities silently lose
        # their derived work (thumbnail / HR zones / geocoded location).
        registry = _register_durable_handlers()
        nets = {net.subscriber_id: net for net in activity_subscriber_registry.ACTIVITY_DURABLE_SUBSCRIBER_NETS}
        healed: set[str] = set()
        exempt: set[str] = set()
        for subscriber_id in registry.subscribers_for(activity_events.ACTIVITY_CREATED):
            net = nets[subscriber_id]
            if net.backfill is not None:
                healed.add(subscriber_id)
            else:
                assert net.exempt_reason, subscriber_id
                exempt.add(subscriber_id)
        assert healed == {
            "activity_thumbnail.generate",
            "activity_streams.compute_hr_zones",
            "activity_geocoding.reverse_geocode",
        }
        assert exempt == {"activity.notify_created"}
