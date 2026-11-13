"""Tests for the sync walk: one keyset order across record types, changes and deletions."""

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import update

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import modules.activities.activity.models as activity_models
import modules.health.health_steps.models as steps_models
import modules.health.health_weight.integration_service as health_weight_integration
import modules.health.health_weight.models as weight_models
import modules.health.models as health_models
import modules.sync.schema as sync_schema
import modules.sync.service as sync_service
from tests._helpers.db import create_sqlite_session
from tests.activities.activity.test_sync import _activity

USER = uuid.UUID("2f6d8b52-47a0-4c3e-9a51-0c1e5d7b8a90")
OTHER_USER = uuid.UUID("7b1c93e4-5d28-4f6a-8e03-a94d2c6f1b57")
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


def _weight(db, day: int, stamp: datetime, user_id: uuid.UUID = USER) -> uuid.UUID:
    row = weight_models.HealthWeight(user_id=user_id, date=date(2026, 1, day), weight_kg=Decimal("70"))
    db.add(row)
    db.flush()
    db.execute(
        update(weight_models.HealthWeight).where(weight_models.HealthWeight.id == row.id).values(updated_at=stamp)
    )
    return row.id


def _steps(db, day: int, stamp: datetime) -> uuid.UUID:
    row = steps_models.HealthSteps(user_id=USER, date=date(2026, 1, day), steps=100)
    db.add(row)
    db.flush()
    db.execute(update(steps_models.HealthSteps).where(steps_models.HealthSteps.id == row.id).values(updated_at=stamp))
    return row.id


def _deleted(db, record_type: str, stamp: datetime) -> uuid.UUID:
    record_id = uuid.uuid4()
    db.add(
        health_models.HealthRecordDeletion(user_id=USER, record_type=record_type, record_id=record_id, deleted_at=stamp)
    )
    db.flush()
    return record_id


def _sync(db, cursor=None, *, types=None, scopes=HEALTH, num_records=100, now=NOW):
    return sync_service.sync(USER, scopes, db, cursor=cursor, types=types, num_records=num_records, now=now)


def _keys(page):
    return [(change.type, change.id, change.record is None) for change in page.changes]


def test_a_first_sync_reports_every_record_oldest_first_across_types(db):
    steps = _steps(db, 1, T1)
    weight = _weight(db, 1, T2)
    _weight(db, 2, T1, user_id=OTHER_USER)

    page = _sync(db)

    assert _keys(page) == [("health_steps", steps, False), ("health_weight", weight, False)]
    assert page.has_more is False
    assert page.changes[1].record.weight_kg == 70


def test_a_deletion_is_reported_with_no_record(db):
    weight = _weight(db, 1, T1)
    gone = _deleted(db, "health_weight", T2)

    page = _sync(db)

    assert _keys(page) == [("health_weight", weight, False), ("health_weight", gone, True)]
    assert page.changes[1].changed_at.replace(tzinfo=UTC) == T2


def test_paging_through_many_ties_misses_and_repeats_nothing(db):
    """A bulk edit stamps many rows alike, so the walk must page through equal stamps by type and id."""
    expected = {("health_weight", _weight(db, day, T1)) for day in range(1, 8)}
    expected |= {("health_steps", _steps(db, day, T1)) for day in range(1, 6)}
    expected |= {
        ("health_weight", _deleted(db, "health_weight", T1)),
        ("health_steps", _deleted(db, "health_steps", T1)),
    }

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
    gone = _deleted(db, "health_weight", T3)

    assert _keys(_sync(db, first.next_cursor)) == [("health_weight", gone, True), ("health_steps", later, False)]


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


def _encrypted(**raw) -> str:
    return core_cryptography.encrypt_token_fernet(json.dumps({"t": NOW.isoformat(), **raw}))


def test_paging_across_sources_misses_and_repeats_nothing(db):
    """Activities and health records both have UUID ids; a cursor holds the id of either."""
    expected = set()
    for day in range(1, 5):
        activity = _activity(user_id=USER, start_time=datetime(2026, 1, day, tzinfo=UTC))
        db.add(activity)
        db.flush()
        db.execute(
            update(activity_models.Activity).where(activity_models.Activity.id == activity.id).values(updated_at=T1)
        )
        expected.add(("activity", activity.id))
        expected.add(("health_weight", _weight(db, day, T1)))
    db.commit()
    scopes = HEALTH | {"activities:read"}

    seen, cursor = [], None
    while True:
        page = _sync(db, cursor, scopes=scopes, num_records=3)
        seen.extend((change.type, change.id) for change in page.changes)
        cursor = page.next_cursor
        if not page.has_more:
            break

    assert len(seen) == len(set(seen)) == len(expected)
    assert set(seen) == expected
    assert {type(record_id) for kind, record_id in seen if kind == "activity"} == {uuid.UUID}
    assert {type(record_id) for kind, record_id in seen if kind == "health_weight"} == {uuid.UUID}


def test_a_tombstone_position_is_a_uuid(db):
    _deleted(db, "health_weight", T1)

    deletions = health_weight_integration.list_health_weight_deletions(USER, None, NOW, 10, db)

    assert [type(d.position[1]) for d in deletions] == [uuid.UUID]


def test_a_cursor_without_the_current_format_is_expired(db):
    old = _encrypted(s=T1.isoformat(), r=0, i=str(uuid.uuid4()))

    with pytest.raises(core_exceptions.SyncExpiredError):
        _sync(db, old)


def test_a_cursor_of_the_previous_format_is_expired(db):
    previous = _encrypted(f=sync_service._CURSOR_FORMAT - 1, s=T1.isoformat(), r=0, i=str(uuid.uuid4()))

    with pytest.raises(core_exceptions.SyncExpiredError):
        _sync(db, previous)


def test_a_cursor_with_an_integer_id_and_no_format_is_expired(db):
    """The format before UUID ids wrote an integer ``i`` and no ``f``; it expires rather than being invalid."""
    old = _encrypted(s=T1.isoformat(), r=0, i=42)

    with pytest.raises(core_exceptions.SyncExpiredError):
        _sync(db, old)


def test_a_current_cursor_with_an_integer_id_is_invalid(db):
    with pytest.raises(core_exceptions.InvalidInputError):
        _sync(db, _encrypted(f=sync_service._CURSOR_FORMAT, s=T1.isoformat(), r=0, i=42))


def test_a_format_3_cursor_is_expired_whatever_it_holds(db):
    old = _encrypted(f=3, s=T1.isoformat(), r=0, i=str(uuid.uuid4()))

    with pytest.raises(core_exceptions.SyncExpiredError):
        _sync(db, old)


_GEAR_RANK = 2 * [source.sync_type for source in sync_service._TYPES].index(sync_schema.SyncType.GEAR)


@pytest.mark.parametrize(
    "raw",
    [
        {"f": sync_service._CURSOR_FORMAT, "s": T1.isoformat(), "r": 2, "i": "not-a-uuid"},
        {"f": sync_service._CURSOR_FORMAT, "s": T1.isoformat(), "r": _GEAR_RANK, "i": "5"},
        {"f": sync_service._CURSOR_FORMAT, "s": T1.isoformat(), "r": 0, "i": "5"},
        {"f": sync_service._CURSOR_FORMAT, "s": T1.isoformat(), "r": 999, "i": "1"},
    ],
)
def test_a_current_cursor_with_a_malformed_id_or_rank_is_invalid(db, raw):
    with pytest.raises(core_exceptions.InvalidInputError):
        _sync(db, _encrypted(**raw))
