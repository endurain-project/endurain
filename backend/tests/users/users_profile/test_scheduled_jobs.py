"""The scheduled sweeps of staged transfer archives, and what the profile registers with the application."""

import os
import time
import uuid

import pytest
from jasil.jobs.registry import JobHandlerRegistry

import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.events as profile_events
import modules.users.users_profile.scheduled_jobs as scheduled_jobs
import modules.users.users_profile.subscriber_registry as subscriber_registry
import modules.users.users_profile.subscribers as profile_subscribers


@pytest.fixture
def storage(_publish_local_platform):
    return _publish_local_platform.storage


def _stage(storage, area, key, *, age_seconds):
    storage.save(area, key, b"zip")
    aged = time.time() - age_seconds
    os.utime(storage._resolve(area, key), (aged, aged))


def test_the_import_sweep_removes_the_archives_past_their_age_and_keeps_the_rest(storage):
    old, fresh = f"{uuid.uuid4()}/old.zip", f"{uuid.uuid4()}/new.zip"
    _stage(
        storage,
        profile_constants.IMPORT_STAGING_AREA,
        old,
        age_seconds=profile_constants.IMPORT_STAGED_MAX_AGE_SECONDS + 60,
    )
    _stage(storage, profile_constants.IMPORT_STAGING_AREA, fresh, age_seconds=0)

    scheduled_jobs.sweep_staged_imports()

    assert storage.list_keys(profile_constants.IMPORT_STAGING_AREA, "") == [fresh]


def test_the_export_sweep_removes_the_archives_past_their_download_window_and_keeps_the_rest(storage):
    old, fresh = f"{uuid.uuid4()}.zip", f"{uuid.uuid4()}.zip"
    _stage(
        storage,
        profile_constants.EXPORT_STAGING_AREA,
        old,
        age_seconds=profile_constants.EXPORT_STAGED_MAX_AGE_SECONDS + 60,
    )
    _stage(storage, profile_constants.EXPORT_STAGING_AREA, fresh, age_seconds=0)

    scheduled_jobs.sweep_staged_exports()

    assert storage.list_keys(profile_constants.EXPORT_STAGING_AREA, "") == [fresh]


def test_both_sweeps_are_scheduled_under_their_own_lock():
    jobs = scheduled_jobs.recurring_jobs()

    assert {job.func for job in jobs} == {scheduled_jobs.sweep_staged_imports, scheduled_jobs.sweep_staged_exports}
    assert {job.lock_name for job in jobs} == {
        scheduled_jobs.STAGED_IMPORT_SWEEP_LOCK,
        scheduled_jobs.STAGED_EXPORT_SWEEP_LOCK,
    }


class TestSubscriberRegistry:
    def test_the_bus_subscribers_deliver_a_transfer_event_to_its_handler(self, _publish_local_platform):
        subscriber_registry.register_bus_subscribers(_publish_local_platform.events)

        assert profile_events.USERS_PROFILE_IMPORT_REQUESTED in _publish_local_platform.events._handlers
        assert profile_events.USERS_PROFILE_EXPORT_REQUESTED in _publish_local_platform.events._handlers

    def test_the_durable_handlers_are_registered_for_both_transfers(self):
        registry = JobHandlerRegistry()

        subscriber_registry.register_durable_handlers(registry)

        assert registry.subscriber_ids() == {
            profile_subscribers.IMPORT_REQUESTED_SUBSCRIBER_ID,
            profile_subscribers.EXPORT_REQUESTED_SUBSCRIBER_ID,
        }

    def test_each_durable_subscriber_declares_why_it_needs_no_reconciliation_net(self):
        declared = {net.subscriber_id for net in subscriber_registry.DURABLE_SUBSCRIBER_NETS}

        assert declared == {
            profile_subscribers.IMPORT_REQUESTED_SUBSCRIBER_ID,
            profile_subscribers.EXPORT_REQUESTED_SUBSCRIBER_ID,
        }
