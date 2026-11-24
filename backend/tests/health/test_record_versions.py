"""Health records are versioned.

The ORM bumps ``version`` on a flush and refuses a write whose version moved, but a bulk ``UPDATE`` skips both, so
the statements that change a row in bulk bump it themselves.
"""

from datetime import date

import pytest
import sqlalchemy as sa

import core.exceptions as core_exceptions
import modules.health.health_steps.schema as steps_schema
import modules.health.health_steps.service as steps_service
import modules.health.health_weight.crud as weight_crud
import modules.health.health_weight.models as weight_models
from tests._factories.health import make_health_weight
from tests._factories.users import make_user

_DAY = date(2026, 10, 1)


def test_an_edit_with_the_version_it_read_succeeds_and_a_stale_one_is_refused(committed_sessions):
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    with committed_sessions() as db:
        created = steps_service.create_health_steps(user.id, steps_schema.HealthStepsCreate(date=_DAY, steps=1000), db)
    assert created.version == 1

    with committed_sessions() as db:
        edited = steps_service.edit_health_steps(
            user.id, created.id, steps_schema.HealthStepsUpdate(steps=2000), db, if_match='"1"'
        )
    assert (edited.steps, edited.version) == (2000, 2)

    with committed_sessions() as db, pytest.raises(core_exceptions.PreconditionFailedError):
        steps_service.edit_health_steps(
            user.id, created.id, steps_schema.HealthStepsUpdate(steps=3000), db, if_match='"1"'
        )


def test_a_bmi_recalculation_in_bulk_changes_the_version(db):
    user = make_user(db)
    record = make_health_weight(db, user.id, date=_DAY, weight_kg=70.0)

    weight_crud.recalculate_bmi_for_user(user.id, 175.0, db)

    stored = db.execute(sa.select(weight_models.HealthWeight.version, weight_models.HealthWeight.bmi)).one()
    assert stored.version == record.version + 1
    assert stored.bmi is not None
