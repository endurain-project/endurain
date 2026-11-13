"""The sync walk over every source against real PostgreSQL: stamps, tombstones and row-value keyset paging."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import update

import modules.activities.activity.models as activity_models
import modules.activities.activity.service as activity_service
import modules.gears.gear.models as gear_models
import modules.gears.gear.service as gear_service
import modules.gears.gear_components.service as gear_components_service
import modules.health.health_weight.models as weight_models
import modules.sync.service as sync_service
from module_registry import configure_gear_contributors
from tests._helpers.db import ensure_user
from tests._helpers.gears import component_create, gear_create
from tests.postgres.test_transaction_ownership import _add_activity

_USER = uuid.UUID("2f6d8b52-47a0-4c3e-9a51-0c1e5d7b8a90")
_OTHER_USER = uuid.UUID("7b1c93e4-5d28-4f6a-8e03-a94d2c6f1b57")
_SCOPES = {"activities:read", "health:read", "health-targets:read", "gears:read"}


@pytest.fixture
def factory(pg_factory):
    configure_gear_contributors()
    ensure_user(pg_factory, _OTHER_USER)
    return pg_factory


def _later() -> datetime:
    """An instant past the settle window of everything the test just wrote."""
    return datetime.now(UTC) + sync_service.SETTLE + timedelta(seconds=5)


def _walk(factory, cursor=None, size=100):
    changes = []
    while True:
        with factory() as db:
            page = sync_service.sync(_USER, _SCOPES, db, cursor=cursor, types=None, num_records=size, now=_later())
        changes.extend((change.type, change.id, change.record is None) for change in page.changes)
        cursor = page.next_cursor
        if not page.has_more:
            return changes, cursor


def test_a_walk_reports_records_of_every_owning_module_and_their_deletions(factory):
    kept = _add_activity(factory, user_id=_USER)
    gone = _add_activity(factory, user_id=_USER)
    _add_activity(factory, user_id=_OTHER_USER)
    with factory() as db:
        gear = gear_service.create_gear(gear_create("Road"), _USER, db)
        component = gear_components_service.create_gear_component(component_create(gear.id), _USER, db)
        db.add(weight_models.HealthWeight(user_id=_USER, date=date(2026, 1, 1), weight_kg=Decimal("70")))
        db.commit()

    first, cursor = _walk(factory)
    assert ("activity", kept, False) in first
    assert ("activity", gone, False) in first
    assert ("gear", gear.id, False) in first
    assert ("gear_component", component.id, False) in first
    assert any(kind == "health_weight" for kind, _, _ in first)
    assert all(not deleted for _, _, deleted in first)

    with factory() as db:
        activity_service.delete_activity(gone, _USER, db, if_match='"1"')
        gear_service.delete_gear(gear.id, _USER, db, if_match=f'"{gear.version}"')

    later, _ = _walk(factory, cursor)
    assert set(later) >= {("activity", gone, True), ("gear", gear.id, True), ("gear_component", component.id, True)}
    # Unassigning the deleted gear stamps nothing it did not change, and the kept activity was untouched.
    assert ("activity", kept, False) not in later


def test_many_rows_on_one_stamp_page_without_gaps_or_repeats(factory):
    ids = [_add_activity(factory, user_id=_USER) for _ in range(7)]
    with factory() as db:
        gears = [gear_service.create_gear(gear_create(f"Bike {n}"), _USER, db).id for n in range(4)]
        stamp = datetime(2026, 1, 1, tzinfo=UTC)
        db.execute(
            update(activity_models.Activity).where(activity_models.Activity.id.in_(ids)).values(updated_at=stamp)
        )
        db.execute(update(gear_models.Gear).where(gear_models.Gear.id.in_(gears)).values(updated_at=stamp))
        weights = [
            weight_models.HealthWeight(user_id=_USER, date=date(2026, 1, 1 + n), weight_kg=Decimal("70"))
            for n in range(5)
        ]
        db.add_all(weights)
        db.flush()
        weight_ids = [weight.id for weight in weights]
        db.execute(
            update(weight_models.HealthWeight)
            .where(weight_models.HealthWeight.id.in_(weight_ids))
            .values(updated_at=stamp)
        )
        db.commit()

    changes, _ = _walk(factory, size=3)

    keys = [(kind, record_id) for kind, record_id, _ in changes]
    assert len(keys) == len(set(keys))
    expected = {("activity", activity_id) for activity_id in ids} | {("gear", gear_id) for gear_id in gears}
    assert expected | {("health_weight", weight_id) for weight_id in weight_ids} <= set(keys)
