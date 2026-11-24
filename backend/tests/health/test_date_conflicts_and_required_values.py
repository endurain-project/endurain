"""A health record is unique per user and day, and its measured value is required.

The database enforces both, so a client that breaks either must be told which rule it broke instead of
getting a server error or a misleading "duplicate" answer.
"""

from datetime import date

import pytest
from pydantic import ValidationError

import core.exceptions as core_exceptions
import modules.health.health_sleep.crud as sleep_crud
import modules.health.health_sleep.schema as sleep_schema
import modules.health.health_steps.crud as steps_crud
import modules.health.health_steps.schema as steps_schema
import modules.health.health_water.crud as water_crud
import modules.health.health_water.schema as water_schema
import modules.health.health_weight.crud as weight_crud
import modules.health.health_weight.schema as weight_schema
from tests._factories import health as health_factories
from tests._factories.users import make_user

_DAY_ONE = date(2026, 1, 1)
_DAY_TWO = date(2026, 1, 2)

# kind -> (make a record, edit a record, update schema, create schema)
_KINDS = {
    "weight": (
        health_factories.make_health_weight,
        weight_crud.edit_health_weight,
        weight_schema.HealthWeightUpdate,
        weight_schema.HealthWeightCreate,
    ),
    "steps": (
        health_factories.make_health_steps,
        steps_crud.edit_health_steps,
        steps_schema.HealthStepsUpdate,
        steps_schema.HealthStepsCreate,
    ),
    "sleep": (
        health_factories.make_health_sleep,
        sleep_crud.edit_health_sleep,
        sleep_schema.HealthSleepUpdate,
        sleep_schema.HealthSleepCreate,
    ),
    "water": (
        health_factories.make_health_water,
        water_crud.edit_health_water,
        water_schema.HealthWaterUpdate,
        water_schema.HealthWaterCreate,
    ),
}
_REQUIRED_VALUE = {"weight": "weight_kg", "steps": "steps", "water": "amount_ml"}


@pytest.mark.parametrize("kind", list(_KINDS))
def test_moving_a_record_onto_a_day_that_has_one_is_a_conflict(db, kind):
    make, edit, update_schema, _ = _KINDS[kind]
    user = make_user(db)
    make(db, user.id, date=_DAY_ONE)
    second = make(db, user.id, date=_DAY_TWO)

    with pytest.raises(core_exceptions.ConflictError):
        edit(user.id, second.id, update_schema(date=_DAY_ONE), db, if_match='"1"')


@pytest.mark.parametrize("kind", list(_REQUIRED_VALUE))
def test_a_record_cannot_be_created_without_its_value(kind):
    create_schema = _KINDS[kind][3]

    with pytest.raises(ValidationError):
        create_schema(date=_DAY_ONE)


@pytest.mark.parametrize("kind", list(_REQUIRED_VALUE))
def test_a_record_cannot_have_its_value_cleared(kind):
    update_schema = _KINDS[kind][2]

    with pytest.raises(ValidationError):
        update_schema(**{_REQUIRED_VALUE[kind]: None})


@pytest.mark.parametrize("kind", list(_REQUIRED_VALUE))
def test_an_edit_that_leaves_the_value_out_is_valid(kind):
    update_schema = _KINDS[kind][2]

    assert update_schema(date=_DAY_ONE).date == _DAY_ONE
