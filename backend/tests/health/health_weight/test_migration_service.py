"""The weight operation data migrations use rewrites a stored record and derives its BMI."""

from datetime import date

import pytest
from tests._helpers.db import create_sqlite_session_factory, ensure_user

import modules.health.health_weight.migration_service as health_weight_migration
import modules.health.health_weight.models as health_weight_models
import modules.health.health_weight.schema as health_weight_schema
import modules.users.users.models as users_models

_USER_ID = 5


@pytest.fixture
def session_factory():
    factory = create_sqlite_session_factory()
    ensure_user(factory, _USER_ID)
    with factory() as db:
        db.get(users_models.Users, _USER_ID).height = 180
        db.commit()
    yield factory
    factory.kw["bind"].dispose()


def test_a_record_without_bmi_is_stored_with_it(session_factory):
    with session_factory() as db:
        row = health_weight_models.HealthWeight(user_id=_USER_ID, date=date(2024, 1, 15), weight_kg=81)
        db.add(row)
        db.commit()
        record_id = row.id

    with session_factory() as db:
        stored = health_weight_migration.get_all_health_weight(db)[0]
        update = health_weight_schema.HealthWeightUpdate.model_validate(stored)

        updated = health_weight_migration.edit_health_weight(_USER_ID, record_id, update, db)

    assert updated.bmi == pytest.approx(25.0)
    with session_factory() as db:
        assert db.get(health_weight_models.HealthWeight, record_id).bmi == pytest.approx(25.0)
