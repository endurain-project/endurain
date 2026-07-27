"""Tests for the shared activities subscriber-registration surface.

Covers the single registration surface used by both the API lifespan and the
standalone worker, plus the reconciliation-net invariant: every durable
subscriber is declared with either a scheduled backfill or a documented
exemption, and every declared backfill is actually scheduled — so a direct
``create_activity`` that publishes no event (e.g. the profile bulk-restore) is
healed instead of silently losing derived work.
"""

from unittest.mock import MagicMock, patch

import core.scheduler as core_scheduler
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

    def test_every_handler_resolves(self):
        registry = _register_durable_handlers()
        for subscriber_id in _registered_durable_ids(registry):
            assert registry.get(subscriber_id) is not None


class TestReconciliationNetInvariant:
    def test_every_registered_subscriber_is_declared(self):
        # A new durable subscriber added to the shared registration but not to the
        # net declaration (or vice versa) fails here — the net decision is forced.
        registry = _register_durable_handlers()
        declared = {net.subscriber_id for net in activity_subscriber_registry.ACTIVITY_DURABLE_SUBSCRIBER_NETS}
        assert _registered_durable_ids(registry) == declared

    def test_each_net_declares_a_backfill_xor_an_exemption(self):
        for net in activity_subscriber_registry.ACTIVITY_DURABLE_SUBSCRIBER_NETS:
            has_backfill = net.backfill is not None
            has_reason = bool(net.exempt_reason)
            # Exactly one: a durable subscriber either ships a backfill net or is an
            # explicitly-justified transient exemption, never both and never neither.
            assert has_backfill != has_reason, net.subscriber_id

    def test_declared_backfills_are_scheduled(self):
        # Drive start_scheduler with a fake scheduler that records every registered
        # job function, then assert each declared reconciliation backfill is wired
        # (declared-but-not-scheduled would be a silent, undetectable net).
        scheduled_funcs: set[object] = set()
        fake_scheduler = MagicMock()
        fake_scheduler.running = True  # skip scheduler.start()
        fake_scheduler.add_job.side_effect = lambda func, *args, **kwargs: scheduled_funcs.add(func)
        with patch.object(core_scheduler, "scheduler", fake_scheduler):
            core_scheduler.start_scheduler()

        nets_with_backfill = [
            net for net in activity_subscriber_registry.ACTIVITY_DURABLE_SUBSCRIBER_NETS if net.backfill
        ]
        assert nets_with_backfill  # sanity: the create-derived subscribers have nets
        for net in nets_with_backfill:
            assert net.backfill in scheduled_funcs, net.subscriber_id

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
