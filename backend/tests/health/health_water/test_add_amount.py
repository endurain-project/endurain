"""The day's water total is capped by the same ``UPDATE`` that adds an intake, on a real session."""

from datetime import date as datetime_date
from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker
from tests._helpers.db import create_sqlite_session, ensure_user

import core.exceptions as core_exceptions
import modules.health.health_water.crud as health_water_crud
import modules.health.health_water.schema as health_water_schema


class TestAddHealthWaterAmountBound:
    """The day's total is checked by the same ``UPDATE`` that adds, on a real session."""

    @pytest.fixture
    def db(self):

        session = create_sqlite_session()
        ensure_user(sessionmaker(bind=session.get_bind()), 1)
        yield session
        session.close()

    def test_an_addition_up_to_the_cap_is_stored(self, db):
        record = health_water_crud.create_health_water(
            1, health_water_schema.HealthWaterCreate(date=datetime_date(2024, 1, 15), amount_ml=19000.0), db
        )

        result = health_water_crud.add_health_water_amount(
            1, record.id, Decimal(health_water_schema.MAX_WATER_ML - 19000), "manual", db
        )

        assert result.amount_ml == health_water_schema.MAX_WATER_ML
        assert result.version == record.version + 1

    def test_an_addition_past_the_cap_is_a_conflict_and_changes_nothing(self, db):
        record = health_water_crud.create_health_water(
            1, health_water_schema.HealthWaterCreate(date=datetime_date(2024, 1, 15), amount_ml=19000.0), db
        )

        with pytest.raises(core_exceptions.ConflictError):
            health_water_crud.add_health_water_amount(1, record.id, Decimal(1001), "manual", db)

        stored = health_water_crud.get_health_water_by_date_and_user_id(1, "2024-01-15", db)
        assert stored is not None
        assert stored.amount_ml == 19000.0
        assert stored.version == record.version

    def test_the_cap_is_the_schema_bound(self):
        with pytest.raises(ValueError):
            health_water_schema.HealthWaterCreate(amount_ml=health_water_schema.MAX_WATER_ML + 1)
