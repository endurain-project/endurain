"""The sync walk over every source against real PostgreSQL: stamps, tombstones and row-value keyset paging."""

from datetime import UTC, date, datetime, timedelta

import pytest

import modules.activities.activity.models as activity_models
import modules.activities.activity.service as activity_service
import modules.gears.gear.models as gear_models
import modules.gears.gear.service as gear_service
import modules.health.health_weight.models as weight_models
import modules.sync.service as sync_service
from tests._factories.activities import make_activity
from tests._factories.gears import make_gear, make_gear_component
from tests._factories.health import make_health_weight
from tests._factories.sync import restamp
from tests._factories.users import make_user

_SCOPES = {"activities:read", "health:read", "health-targets:read", "gears:read"}


@pytest.fixture
def user(db):
    created = make_user(db)
    db.flush()
    return created.id


def _later() -> datetime:
    """An instant past the settle window of everything the test just wrote."""
    return datetime.now(UTC) + sync_service.SETTLE + timedelta(seconds=5)


def _walk(db, user, cursor=None, size=100):
    changes = []
    while True:
        page = sync_service.sync(user, _SCOPES, db, cursor=cursor, types=None, num_records=size, now=_later())
        changes.extend((change.type, change.id, change.record is None) for change in page.changes)
        cursor = page.next_cursor
        if not page.has_more:
            return changes, cursor


def test_a_walk_reports_records_of_every_owning_module_and_their_deletions(committed_sessions):
    """Each step commits, so the stamps differ as they do in production (one transaction stamps every row alike)."""
    with committed_sessions() as db:
        user, other = make_user(db).id, make_user(db).id
        kept, gone = make_activity(db, user).id, make_activity(db, user).id
        others = make_activity(db, other).id
        gear = make_gear(db, user, nickname="Road")
        component = make_gear_component(db, user, gear.id)
        make_health_weight(db, user, date=date(2026, 1, 1))
        db.commit()

    with committed_sessions() as db:
        first, cursor = _walk(db, user)
    assert ("activity", kept, False) in first
    assert ("activity", gone, False) in first
    assert ("gear", gear.id, False) in first
    assert ("gear_component", component.id, False) in first
    assert any(kind == "health_weight" for kind, _, _ in first)
    assert all(not deleted for _, _, deleted in first)
    assert others not in {record_id for _, record_id, _ in first}

    with committed_sessions() as db:
        activity_service.delete_activity(gone, user, db, if_match='"1"')
    with committed_sessions() as db:
        gear_service.delete_gear(gear.id, user, db, if_match=f'"{gear.version}"')

    with committed_sessions() as db:
        later, _ = _walk(db, user, cursor)
    assert set(later) >= {("activity", gone, True), ("gear", gear.id, True), ("gear_component", component.id, True)}
    # Unassigning the deleted gear stamps nothing it did not change, and the kept activity was untouched.
    assert ("activity", kept, False) not in later


def test_many_rows_on_one_stamp_page_without_gaps_or_repeats(db, user):
    ids = [make_activity(db, user).id for _ in range(7)]
    gears = [make_gear(db, user, nickname=f"Bike {n}").id for n in range(4)]
    weights = [make_health_weight(db, user, date=date(2026, 1, 1 + n)).id for n in range(5)]
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    restamp(db, activity_models.Activity, ids, stamp)
    restamp(db, gear_models.Gear, gears, stamp)
    restamp(db, weight_models.HealthWeight, weights, stamp)

    changes, _ = _walk(db, user, size=3)

    keys = [(kind, record_id) for kind, record_id, _ in changes]
    assert len(keys) == len(set(keys))
    expected = {("activity", activity_id) for activity_id in ids} | {("gear", gear_id) for gear_id in gears}
    assert expected | {("health_weight", weight_id) for weight_id in weights} <= set(keys)
