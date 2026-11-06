"""The bulk BMI recalculation against real PostgreSQL, where a tiny height used to divide by zero."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

import modules.health.health_weight.crud as weight_crud
import modules.health.health_weight.models as weight_models
from tests._helpers.db import ensure_user

_DAY = date(2026, 10, 1)


@pytest.fixture
def factory(pg_factory):
    ensure_user(pg_factory, 1)
    return pg_factory


@pytest.mark.postgres
@pytest.mark.parametrize(("height", "expected"), [(5.0, None), (178.0, Decimal("22.25")), (70.0, None)])
def test_a_recalculation_neither_divides_by_zero_nor_stores_an_out_of_range_bmi(factory, height, expected):
    with factory() as db:
        db.add(weight_models.HealthWeight(user_id=1, date=_DAY, weight_kg=Decimal("70.5"), bmi=Decimal(20)))
        db.commit()

    with factory() as db:
        weight_crud.recalculate_bmi_for_user(1, height, db)
        db.commit()

    with factory() as db:
        assert db.scalar(select(weight_models.HealthWeight.bmi)) == expected
