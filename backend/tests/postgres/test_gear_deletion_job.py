"""The gear deletion job unassigns the gear in batches and deletes it, against real PostgreSQL."""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select, update

import modules.activities.activity.models as activity_models
import modules.gears.gear.crud as gear_crud
import modules.gears.gear.deletion_job_service as job_service
import modules.gears.gear.service as gear_service
from module_registry import configure_gear_contributors
from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.db import ensure_user
from tests._helpers.gears import gear_create
from tests.postgres.test_transaction_ownership import _add_activity

_MODULE = "modules.gears.gear.deletion_job_service"


@pytest.fixture
def factory(pg_factory):
    ensure_user(pg_factory, MOCK_USER_ID)
    configure_gear_contributors()
    return pg_factory


def _gear_with_activities(factory, count: int) -> tuple[uuid.UUID, list[uuid.UUID]]:
    with factory() as db:
        gear_id = gear_service.create_gear(gear_create(), MOCK_USER_ID, db).id
    ids = [_add_activity(factory, user_id=MOCK_USER_ID) for _ in range(count)]
    with factory() as db:
        db.execute(update(activity_models.Activity).where(activity_models.Activity.id.in_(ids)).values(gear_id=gear_id))
        db.commit()
    return gear_id, ids


def _run(factory, gear_id, *, batch: int):
    with (
        patch(f"{_MODULE}.core_database.SessionLocal", factory),
        patch.object(job_service.gears_constants, "DELETION_BATCH_SIZE", batch),
    ):
        return job_service._apply(MOCK_USER_ID, gear_id)


def test_the_gear_is_unassigned_across_batches_and_deleted(factory):
    gear_id, ids = _gear_with_activities(factory, 5)
    with factory() as db:
        versions = dict(db.execute(select(activity_models.Activity.id, activity_models.Activity.version)).all())

    unassigned, deleted = _run(factory, gear_id, batch=2)

    assert deleted is True
    # The batches take two, two and one; the last one is short, so nothing is left for the final transaction.
    assert unassigned == 5
    with factory() as db:
        assert gear_crud.get_gear_user_by_id(MOCK_USER_ID, gear_id, db) is None
        rows = db.execute(
            select(activity_models.Activity.id, activity_models.Activity.gear_id, activity_models.Activity.version)
        ).all()
    assert {row.id for row in rows} == set(ids)
    assert all(row.gear_id is None and row.version == versions[row.id] + 1 for row in rows)


def test_running_the_job_again_after_the_gear_is_gone_succeeds_without_changes(factory):
    gear_id, _ = _gear_with_activities(factory, 3)
    _run(factory, gear_id, batch=2)

    unassigned, deleted = _run(factory, gear_id, batch=2)

    assert (unassigned, deleted) == (0, False)
