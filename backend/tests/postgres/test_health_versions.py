"""Health records are versioned against real PostgreSQL.

The ORM bumps ``version`` on a flush and refuses a write whose version moved, but a bulk
``UPDATE`` skips both, so the statements that change a row in bulk bump it themselves.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

import core.exceptions as core_exceptions
import modules.health.health_steps.schema as steps_schema
import modules.health.health_steps.service as steps_service
import modules.health.health_weight.crud as weight_crud
import modules.health.health_weight.models as weight_models
from tests._helpers.db import ensure_user

_DAY = date(2026, 10, 1)


_USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture
def factory(pg_factory):
    ensure_user(pg_factory, _USER_ID)
    return pg_factory


def test_an_edit_with_the_version_it_read_succeeds_and_a_stale_one_is_refused(factory):
    with factory() as db:
        created = steps_service.create_health_steps(_USER_ID, steps_schema.HealthStepsCreate(date=_DAY, steps=1000), db)
    assert created.version == 1

    with factory() as db:
        edited = steps_service.edit_health_steps(
            _USER_ID, created.id, steps_schema.HealthStepsUpdate(steps=2000), db, if_match='"1"'
        )
    assert (edited.steps, edited.version) == (2000, 2)

    with factory() as db, pytest.raises(core_exceptions.PreconditionFailedError):
        steps_service.edit_health_steps(
            _USER_ID, created.id, steps_schema.HealthStepsUpdate(steps=3000), db, if_match='"1"'
        )


def test_a_bmi_recalculation_in_bulk_changes_the_version(factory):
    with factory() as db:
        db.add(weight_models.HealthWeight(user_id=_USER_ID, date=_DAY, weight_kg=Decimal(70), bmi=Decimal(20)))
        db.commit()

    with factory() as db:
        weight_crud.recalculate_bmi_for_user(_USER_ID, 175.0, db)
        db.commit()

    with factory() as db:
        assert db.scalar(select(weight_models.HealthWeight.version)) == 2
