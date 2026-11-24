"""The sync walk on the real database: one keyset order across record types, changes and deletions."""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import modules.activities.activity.models as activity_models
import modules.health.health_steps.models as steps_models
import modules.health.health_weight.integration_service as health_weight_integration
import modules.health.health_weight.models as weight_models
import modules.sync.schema as sync_schema
import modules.sync.service as sync_service
from tests._factories.activities import make_activity
from tests._factories.health import make_health_steps, make_health_weight
from tests._factories.sync import make_health_tombstone, restamp
from tests._factories.users import make_user

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 1, 1, tzinfo=UTC)
T2 = datetime(2026, 2, 1, tzinfo=UTC)
T3 = datetime(2026, 3, 1, tzinfo=UTC)
HEALTH = {"health:read"}


@pytest.fixture
def user(db):
    created = make_user(db)
    db.flush()
    return created.id


@pytest.fixture
def other(db):
    created = make_user(db)
    db.flush()
    return created.id


def _weight(db, user_id, day: int, stamp: datetime) -> uuid.UUID:
    record = make_health_weight(db, user_id, date=datetime(2026, 1, day).date(), weight_kg=70)
    restamp(db, weight_models.HealthWeight, [record.id], stamp)
    return record.id


def _steps(db, user_id, day: int, stamp: datetime) -> uuid.UUID:
    record = make_health_steps(db, user_id, date=datetime(2026, 1, day).date(), steps=100)
    restamp(db, steps_models.HealthSteps, [record.id], stamp)
    return record.id


def _sync(db, user, cursor=None, *, types=None, scopes=HEALTH, num_records=100, now=NOW):
    return sync_service.sync(user, scopes, db, cursor=cursor, types=types, num_records=num_records, now=now)


def _keys(page):
    return [(change.type, change.id, change.record is None) for change in page.changes]


def _walk(db, user, *, scopes=HEALTH, num_records=3):
    seen, cursor, pages = [], None, 0
    while True:
        page = _sync(db, user, cursor, scopes=scopes, num_records=num_records)
        seen.extend((change.type, change.id) for change in page.changes)
        cursor, pages = page.next_cursor, pages + 1
        if not page.has_more:
            return seen, pages


def test_a_first_sync_reports_every_record_oldest_first_across_types(db, user, other):
    steps = _steps(db, user, 1, T1)
    weight = _weight(db, user, 1, T2)
    _weight(db, other, 2, T1)

    page = _sync(db, user)

    assert _keys(page) == [("health_steps", steps, False), ("health_weight", weight, False)]
    assert page.has_more is False
    assert page.changes[1].record.weight_kg == 70


def test_a_deletion_is_reported_with_no_record(db, user):
    weight = _weight(db, user, 1, T1)
    gone = make_health_tombstone(db, user, "health_weight", T2)

    page = _sync(db, user)

    assert _keys(page) == [("health_weight", weight, False), ("health_weight", gone, True)]
    assert page.changes[1].changed_at.replace(tzinfo=UTC) == T2


def test_another_users_deletion_is_not_reported(db, user, other):
    make_health_tombstone(db, other, "health_weight", T1)

    assert _sync(db, user).changes == []


def test_paging_through_many_ties_misses_and_repeats_nothing(db, user):
    """A bulk edit stamps many rows alike, so the walk must page through equal stamps by type and id."""
    expected = {("health_weight", _weight(db, user, day, T1)) for day in range(1, 8)}
    expected |= {("health_steps", _steps(db, user, day, T1)) for day in range(1, 6)}
    expected |= {
        ("health_weight", make_health_tombstone(db, user, "health_weight", T1)),
        ("health_steps", make_health_tombstone(db, user, "health_steps", T1)),
    }

    seen, pages = _walk(db, user)

    assert len(seen) == len(set(seen)) == len(expected)
    assert set(seen) == expected
    assert pages == 5


def test_the_cursor_of_a_finished_walk_reports_only_later_changes(db, user):
    _weight(db, user, 1, T1)
    first = _sync(db, user)
    assert _sync(db, user, first.next_cursor).changes == []

    later = _steps(db, user, 1, T3)
    gone = make_health_tombstone(db, user, "health_weight", T3)

    assert _keys(_sync(db, user, first.next_cursor)) == [
        ("health_weight", gone, True),
        ("health_steps", later, False),
    ]


def test_a_change_inside_the_settle_window_waits_for_a_later_sync(db, user):
    fresh = _weight(db, user, 1, NOW - timedelta(seconds=30))

    assert _sync(db, user).changes == []
    assert _keys(_sync(db, user, now=NOW + sync_service.SETTLE)) == [("health_weight", fresh, False)]


def test_an_empty_page_keeps_the_position_and_renews_the_cursor(db, user):
    _weight(db, user, 1, T1)
    cursor = _sync(db, user).next_cursor
    later = NOW + timedelta(days=80)

    renewed = _sync(db, user, cursor, now=later).next_cursor
    _steps(db, user, 1, T2 + timedelta(days=1))

    # 80 days on, the renewed cursor is still fresh where the old one expires 20 days later.
    assert len(_sync(db, user, renewed, now=later + timedelta(days=20)).changes) == 1
    with pytest.raises(core_exceptions.SyncExpiredError):
        _sync(db, user, cursor, now=later + timedelta(days=20))


def test_types_limit_the_walk(db, user):
    _weight(db, user, 1, T1)
    steps = _steps(db, user, 1, T2)

    page = _sync(db, user, types={sync_schema.SyncType.HEALTH_STEPS})

    assert _keys(page) == [("health_steps", steps, False)]


def test_a_type_without_its_scope_is_left_out_unless_asked_for(db, user):
    _weight(db, user, 1, T1)

    assert _sync(db, user, scopes={"gears:read"}).changes == []
    with pytest.raises(core_exceptions.PermissionDeniedError):
        _sync(db, user, types={sync_schema.SyncType.HEALTH_WEIGHT}, scopes={"gears:read"})


def test_a_cursor_the_server_did_not_issue_is_refused(db, user):
    with pytest.raises(core_exceptions.InvalidInputError):
        _sync(db, user, "not-a-cursor")


def _encrypted(**raw) -> str:
    return core_cryptography.encrypt_token_fernet(json.dumps({"t": NOW.isoformat(), **raw}))


def test_paging_across_sources_misses_and_repeats_nothing(db, user):
    """Activities and health records both have UUID ids; a cursor holds the id of either."""
    expected = set()
    for day in range(1, 5):
        activity = make_activity(
            db,
            user,
            start_time=datetime(2026, 1, day, 8, tzinfo=UTC),
            end_time=datetime(2026, 1, day, 9, tzinfo=UTC),
        )
        restamp(db, activity_models.Activity, [activity.id], T1)
        expected.add(("activity", activity.id))
        expected.add(("health_weight", _weight(db, user, day, T1)))

    seen, _ = _walk(db, user, scopes=HEALTH | {"activities:read"})

    assert len(seen) == len(set(seen)) == len(expected)
    assert set(seen) == expected
    assert {type(record_id) for _, record_id in seen} == {uuid.UUID}


def test_a_tombstone_position_is_a_uuid(db, user):
    make_health_tombstone(db, user, "health_weight", T1)

    deletions = health_weight_integration.list_health_weight_deletions(user, None, NOW, 10, db)

    assert [type(d.position[1]) for d in deletions] == [uuid.UUID]


@pytest.mark.parametrize("fmt", [None, 3, sync_service._CURSOR_FORMAT - 1])
def test_a_cursor_of_another_format_is_expired_whatever_it_holds(db, user, fmt):
    raw = {"s": T1.isoformat(), "r": 0, "i": str(uuid.uuid4())}
    if fmt is not None:
        raw["f"] = fmt

    with pytest.raises(core_exceptions.SyncExpiredError):
        _sync(db, user, _encrypted(**raw))


def test_a_current_cursor_with_an_integer_id_is_invalid(db, user):
    with pytest.raises(core_exceptions.InvalidInputError):
        _sync(db, user, _encrypted(f=sync_service._CURSOR_FORMAT, s=T1.isoformat(), r=0, i=42))


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
def test_a_current_cursor_with_a_malformed_id_or_rank_is_invalid(db, user, raw):
    with pytest.raises(core_exceptions.InvalidInputError):
        _sync(db, user, _encrypted(**raw))
