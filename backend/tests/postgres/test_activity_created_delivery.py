"""``activity.created`` commits atomically with the activity, in both delivery modes.

``store_parsed_activity`` only stages the activity and its event; the caller's
commit makes them durable. With durable jobs on, the outbox row has to join that
same transaction. With them off, the event has to reach the bus only after the
commit, and never for work that was rolled back. Only per-session connections can
show it: another session sees nothing until the commit.
"""

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import jasil.jobs.registry as jobs_registry
import jasil.settings as jasil_settings
import jasil.testing as jasil_testing
import pytest
from sqlalchemy import func, select, text

import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.events as activity_events
import modules.activities.activity.integration_service as activity_integration
import modules.activities.activity.models as activity_models
from tests._helpers.db import ensure_user

_USER_ID = 1
_PRIVACY_FLAGS = (
    "hide_start_time",
    "hide_location",
    "hide_map",
    "hide_hr",
    "hide_power",
    "hide_cadence",
    "hide_elevation",
    "hide_speed",
    "hide_pace",
    "hide_laps",
    "hide_workout_sets_steps",
    "hide_gear",
)


@pytest.fixture(params=["durable", "best_effort"])
def mode(request, pg_factory, tmp_path):
    """A published platform in the requested delivery mode, plus the bus events it dispatched."""
    durable = request.param == "durable"
    settings = jasil_settings.JasilSettings(jobs=jasil_settings.JobSettings(enabled=durable))
    platform = jasil_testing.install_test_platform(tmp_path, settings=settings)
    if durable:
        jobs_registry.registry.register(activity_events.ACTIVITY_CREATED, "test.activity_created", lambda _event: None)
    dispatched: list = []
    platform.events.subscribe(activity_events.ACTIVITY_CREATED, dispatched.append)
    ensure_user(pg_factory, _USER_ID)
    return request.param, dispatched


def _parsed(dedup_key: str, name: str = "Ride") -> activity_contracts.ParsedActivity:
    start = datetime(2026, 7, 28, 9, 0, tzinfo=UTC)
    return activity_contracts.ParsedActivity(
        activity=activity_contracts.ActivityCore(
            user_id=_USER_ID,
            name=name,
            distance=1000,
            activity_type=1,
            start_time=start,
            end_time=start + timedelta(hours=1),
            total_elapsed_time=3600.0,
            total_timer_time=3540.0,
            **{flag: False for flag in _PRIVACY_FLAGS},
        ),
        components={},
        source=activity_contracts.ImportSource(kind="upload", dedup_key=dedup_key),
    )


def _wait_until(condition: Callable[[], bool], timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return condition()


def _committed_activities(factory) -> int:
    """Count activities through a fresh session, so only committed rows are visible."""
    with factory() as db:
        return db.scalar(select(func.count()).select_from(activity_models.Activity)) or 0


def _committed_outbox_rows(factory, activity_id: int) -> int:
    with factory() as db:
        return (
            db.execute(
                text(
                    "SELECT count(*) FROM event_outbox WHERE event_type = :event_type "
                    "AND (payload ->> 'activity_id')::int = :activity_id"
                ),
                {"event_type": activity_events.ACTIVITY_CREATED, "activity_id": activity_id},
            ).scalar_one()
            or 0
        )


def _bus_events_for(dispatched: list, activity_id: int) -> int:
    return sum(1 for event in dispatched if event.payload.get("activity_id") == activity_id)


def test_nothing_is_visible_or_delivered_before_the_commit(mode, pg_factory):
    _mode, dispatched = mode
    with pg_factory() as db:
        stored = activity_integration.store_parsed_activity(_parsed("staged"), db)

        assert _committed_activities(pg_factory) == 0
        assert _committed_outbox_rows(pg_factory, stored.id) == 0
        assert dispatched == []


def test_a_rolled_back_unit_of_work_leaves_no_activity_and_no_event(mode, pg_factory):
    _mode, dispatched = mode
    with pg_factory() as db:
        stored = activity_integration.store_parsed_activity(_parsed("rolled-back"), db)
        db.rollback()

    time.sleep(0.3)
    assert _committed_activities(pg_factory) == 0
    assert _committed_outbox_rows(pg_factory, stored.id) == 0
    assert dispatched == []


def test_a_session_closed_without_committing_leaves_nothing(mode, pg_factory):
    """The crash-before-commit case: the staged work and its event vanish together."""
    _mode, dispatched = mode
    db = pg_factory()
    stored = activity_integration.store_parsed_activity(_parsed("abandoned"), db)
    db.close()

    time.sleep(0.3)
    assert _committed_activities(pg_factory) == 0
    assert _committed_outbox_rows(pg_factory, stored.id) == 0
    assert dispatched == []


def test_the_commit_makes_the_activity_and_its_event_durable_together(mode, pg_factory):
    delivery, dispatched = mode
    with pg_factory() as db:
        stored = activity_integration.store_parsed_activity(_parsed("committed"), db)
        db.commit()

    assert _committed_activities(pg_factory) == 1
    if delivery == "durable":
        assert _committed_outbox_rows(pg_factory, stored.id) == 1
        time.sleep(0.3)
        assert dispatched == [], "the durable route must not also dispatch on the bus"
    else:
        assert _wait_until(lambda: _bus_events_for(dispatched, stored.id) == 1)
        assert _committed_outbox_rows(pg_factory, stored.id) == 0


def test_a_reimport_stages_no_second_event(mode, pg_factory):
    delivery, dispatched = mode
    with pg_factory() as db:
        first = activity_integration.store_parsed_activity(_parsed("same-key"), db)
        db.commit()
    with pg_factory() as db:
        second = activity_integration.store_parsed_activity(_parsed("same-key"), db)
        db.commit()

    assert second.id == first.id
    assert _committed_activities(pg_factory) == 1
    if delivery == "durable":
        assert _committed_outbox_rows(pg_factory, first.id) == 1
    else:
        assert _wait_until(lambda: _bus_events_for(dispatched, first.id) == 1)
        time.sleep(0.3)
        assert _bus_events_for(dispatched, first.id) == 1


def test_concurrent_imports_of_one_activity_store_it_once_and_publish_once(mode, pg_factory):
    """The dedup read-then-write races; the unique index picks one winner and the losers return it."""
    import threading

    delivery, dispatched = mode
    barrier = threading.Barrier(6)
    ids: list[int] = []
    errors: list[BaseException] = []

    def import_it() -> None:
        try:
            barrier.wait()
            with pg_factory() as db:
                stored = activity_integration.store_parsed_activity(_parsed("raced"), db)
                db.commit()
                ids.append(stored.id)
        except BaseException as err:
            errors.append(err)

    threads = [threading.Thread(target=import_it) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert errors == []
    assert len(set(ids)) == 1
    assert _committed_activities(pg_factory) == 1
    if delivery == "durable":
        assert _committed_outbox_rows(pg_factory, ids[0]) == 1
    else:
        assert _wait_until(lambda: _bus_events_for(dispatched, ids[0]) >= 1)
        time.sleep(0.3)
        assert _bus_events_for(dispatched, ids[0]) == 1
