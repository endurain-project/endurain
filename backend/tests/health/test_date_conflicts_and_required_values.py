"""A health record is unique per user and day, and its measured value is required.

The database enforces both, so a client that breaks either must be told which rule it broke instead of
getting a server error or a misleading "duplicate" answer.
"""

from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker
from tests._helpers.db import create_sqlite_session, ensure_user

import core.exceptions as core_exceptions
import modules.health.health_sleep.crud as sleep_crud
import modules.health.health_sleep.schema as sleep_schema
import modules.health.health_steps.crud as steps_crud
import modules.health.health_steps.schema as steps_schema
import modules.health.health_water.crud as water_crud
import modules.health.health_water.schema as water_schema
import modules.health.health_weight.crud as weight_crud
import modules.health.health_weight.schema as weight_schema
import modules.health.record_crud as health_record_crud

_DAY_ONE = date(2026, 1, 1)
_DAY_TWO = date(2026, 1, 2)

# kind -> (create function, edit function, create schema, update schema, values of a record)
_KINDS = {
    "weight": (
        weight_crud.create_health_weight,
        weight_crud.edit_health_weight,
        weight_schema.HealthWeightCreate,
        weight_schema.HealthWeightUpdate,
        {"weight": 70.0},
    ),
    "steps": (
        steps_crud.create_health_steps,
        steps_crud.edit_health_steps,
        steps_schema.HealthStepsCreate,
        steps_schema.HealthStepsUpdate,
        {"steps": 1000},
    ),
    "sleep": (
        sleep_crud.create_health_sleep,
        sleep_crud.edit_health_sleep,
        sleep_schema.HealthSleepCreate,
        sleep_schema.HealthSleepUpdate,
        {},
    ),
    "water": (
        water_crud.create_health_water,
        water_crud.edit_health_water,
        water_schema.HealthWaterCreate,
        water_schema.HealthWaterUpdate,
        {"amount_ml": 250.0},
    ),
}
_REQUIRED_VALUE = {"weight": "weight", "steps": "steps", "water": "amount_ml"}


@pytest.fixture
def db():
    session = create_sqlite_session()
    ensure_user(sessionmaker(bind=session.get_bind()), 1)
    yield session
    session.close()


@pytest.mark.parametrize("kind", ["weight", "steps", "water"])
def test_moving_a_record_onto_a_day_that_has_one_is_a_conflict(db, kind):
    create, edit, create_schema, update_schema, values = _KINDS[kind]
    create(1, create_schema(date=_DAY_ONE, **values), db)
    second = create(1, create_schema(date=_DAY_TWO, **values), db)

    with pytest.raises(core_exceptions.ConflictError):
        edit(1, second.id, update_schema(date=_DAY_ONE), db, if_match="*")


@pytest.mark.parametrize("kind", list(_REQUIRED_VALUE))
def test_a_record_cannot_be_created_without_its_value(kind):
    _, _, create_schema, _, _ = _KINDS[kind]

    with pytest.raises(ValidationError):
        create_schema(date=_DAY_ONE)


@pytest.mark.parametrize("kind", list(_REQUIRED_VALUE))
def test_a_record_cannot_have_its_value_cleared(kind):
    _, _, _, update_schema, _ = _KINDS[kind]

    with pytest.raises(ValidationError):
        update_schema(**{_REQUIRED_VALUE[kind]: None})


@pytest.mark.parametrize("kind", list(_REQUIRED_VALUE))
def test_an_edit_that_leaves_the_value_out_is_valid(kind):
    _, _, _, update_schema, _ = _KINDS[kind]

    update_schema(date=_DAY_ONE)


def test_a_sleep_record_moved_onto_a_day_that_has_one_is_a_conflict(mock_db):
    """The sleep date is a string the SQLite test database cannot store, so the clash is simulated."""
    from unittest.mock import MagicMock, patch

    from sqlalchemy.exc import IntegrityError

    mock_db.flush.side_effect = IntegrityError("insert", {}, Exception("unique"))
    with (
        patch.object(health_record_crud, "get_owned", return_value=MagicMock(version=1)),
        pytest.raises(core_exceptions.ConflictError),
    ):
        sleep_crud.edit_health_sleep(1, 5, sleep_schema.HealthSleepUpdate(date=_DAY_ONE), mock_db, if_match="1")
