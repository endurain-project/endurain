"""Tests for the sync walk: one keyset order across record types, changes and deletions."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import update

import core.exceptions as core_exceptions
import modules.health.health_steps.models as steps_models
import modules.health.health_weight.models as weight_models
import modules.health.models as health_models
import modules.sync.schema as sync_schema
import modules.sync.service as sync_service
from tests._helpers.db import create_sqlite_session

USER = 1
NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 1, 1, tzinfo=UTC)
T2 = datetime(2026, 2, 1, tzinfo=UTC)
T3 = datetime(2026, 3, 1, tzinfo=UTC)
HEALTH = {"health:read"}


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()


def _weight(db, day: int, stamp: datetime, user_id: int = USER) -> int:
    row = weight_models.HealthWeight(user_id=user_id, date=date(2026, 1, day), weight_kg=Decimal("70"))
    db.add(row)
    db.flush()
    db.execute(
        update(weight_models.HealthWeight).where(weight_models.HealthWeight.id == row.id).values(updated_at=stamp)
    )
    return row.id


def _steps(db, day: int, stamp: datetime) -> int:
    row = steps_models.HealthSteps(user_id=USER, date=date(2026, 1, day), steps=100)
    db.add(row)
    db.flush()
    db.execute(update(steps_models.HealthSteps).where(steps_models.HealthSteps.id == row.id).values(updated_at=stamp))
    return row.id


def _deleted(db, record_type: str, record_id: int, stamp: datetime) -> None:
    db.add(
        health_models.HealthRecordDeletion(user_id=USER, record_type=record_type, record_id=record_id, deleted_at=stamp)
    )
    db.flush()


def _sync(db, cursor=None, *, types=None, scopes=HEALTH, num_records=100, now=NOW):
    return sync_service.sync(USER, scopes, db, cursor=cursor, types=types, num_records=num_records, now=now)


def _keys(page):
    return [(change.type, change.id, change.record is None) for change in page.changes]


def test_a_first_sync_reports_every_record_oldest_first_across_types(db):
    steps = _steps(db, 1, T1)
    weight = _weight(db, 1, T2)
    _weight(db, 2, T1, user_id=2)

    page = _sync(db)

    assert _keys(page) == [("health_steps", steps, False), ("health_weight", weight, False)]
    assert page.has_more is False
    assert page.changes[1].record.weight_kg == 70


def test_a_deletion_is_reported_with_no_record(db):
    weight = _weight(db, 1, T1)
    _deleted(db, "health_weight", 999, T2)

    page = _sync(db)

    assert _keys(page) == [("health_weight", weight, False), ("health_weight", 999, True)]
    assert page.changes[1].changed_at.replace(tzinfo=UTC) == T2


def test_paging_through_many_ties_misses_and_repeats_nothing(db):
    """A bulk edit stamps many rows alike, so the walk must page through equal stamps by type and id."""
    expected = {("health_weight", _weight(db, day, T1)) for day in range(1, 8)}
    expected |= {("health_steps", _steps(db, day, T1)) for day in range(1, 6)}
    _deleted(db, "health_weight", 500, T1)
    _deleted(db, "health_steps", 501, T1)
    expected |= {("health_weight", 500), ("health_steps", 501)}

    seen, cursor, pages = [], None, 0
    while True:
        page = _sync(db, cursor, num_records=3)
        seen.extend((change.type, change.id) for change in page.changes)
        cursor, pages = page.next_cursor, pages + 1
        if not page.has_more:
            break

    assert len(seen) == len(set(seen)) == len(expected)
    assert set(seen) == expected
    assert pages == 5


def test_the_cursor_of_a_finished_walk_reports_only_later_changes(db):
    _weight(db, 1, T1)
    first = _sync(db)
    assert _sync(db, first.next_cursor).changes == []

    later = _steps(db, 1, T3)
    _deleted(db, "health_weight", 77, T3)

    assert _keys(_sync(db, first.next_cursor)) == [("health_weight", 77, True), ("health_steps", later, False)]


def test_a_change_inside_the_settle_window_waits_for_a_later_sync(db):
    fresh = _weight(db, 1, NOW - timedelta(seconds=30))

    assert _sync(db).changes == []
    assert _keys(_sync(db, now=NOW + sync_service.SETTLE)) == [("health_weight", fresh, False)]


def test_an_empty_page_keeps_the_position_and_renews_the_cursor(db):
    _weight(db, 1, T1)
    cursor = _sync(db).next_cursor
    later = NOW + timedelta(days=80)

    renewed = _sync(db, cursor, now=later).next_cursor
    _steps(db, 1, T2 + timedelta(days=1))

    # 80 days on, the renewed cursor is still fresh where the old one expires 20 days later.
    assert len(_sync(db, renewed, now=later + timedelta(days=20)).changes) == 1
    with pytest.raises(core_exceptions.SyncExpiredError):
        _sync(db, cursor, now=later + timedelta(days=20))


def test_types_limit_the_walk(db):
    _weight(db, 1, T1)
    steps = _steps(db, 1, T2)

    page = _sync(db, types={sync_schema.SyncType.HEALTH_STEPS})

    assert _keys(page) == [("health_steps", steps, False)]


def test_a_type_without_its_scope_is_left_out_unless_asked_for(db):
    _weight(db, 1, T1)

    assert _sync(db, scopes={"gears:read"}).changes == []
    with pytest.raises(core_exceptions.PermissionDeniedError):
        _sync(db, types={sync_schema.SyncType.HEALTH_WEIGHT}, scopes={"gears:read"})


def test_a_cursor_the_server_did_not_issue_is_refused(db):
    with pytest.raises(core_exceptions.InvalidInputError):
        _sync(db, "not-a-cursor")
