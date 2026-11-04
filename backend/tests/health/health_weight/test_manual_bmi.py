"""A manually entered weight never carries a client-sent BMI; a provider's own BMI is kept."""

from datetime import date

import pytest
from sqlalchemy.orm import sessionmaker
from tests._helpers.db import create_sqlite_session, ensure_user

import modules.health.health_weight.integration_service as weight_integration
import modules.health.health_weight.schema as weight_schema
import modules.health.health_weight.service as weight_service
import modules.users.users.models as users_models

_DAY = date(2024, 1, 15)


def _set_height(db, height):
    user = db.get(users_models.Users, 1)
    user.height = height
    db.commit()


@pytest.fixture
def db():
    session = create_sqlite_session()
    ensure_user(sessionmaker(bind=session.get_bind()), 1)
    _set_height(session, 175)
    yield session
    session.close()


def _create(db, bmi=None, weight=75.0, day=_DAY):
    return weight_service.create_health_weight(
        1, weight_schema.HealthWeightCreate(date=day, weight=weight, bmi=bmi), db
    )


class TestManualCreate:
    def test_a_client_bmi_is_replaced_by_the_derived_one(self, db):
        stored = _create(db, bmi=5.0)

        assert stored.bmi == pytest.approx(75.0 / 1.75**2, abs=0.01)

    def test_the_bmi_is_derived_when_none_is_sent(self, db):
        assert _create(db).bmi == pytest.approx(75.0 / 1.75**2, abs=0.01)

    def test_without_a_height_the_bmi_is_empty_whatever_the_client_sent(self, db):
        _set_height(db, None)

        assert _create(db, bmi=22.0).bmi is None


class TestManualEdit:
    def _edit(self, db, record, **changes):
        return weight_service.edit_health_weight(
            1, record.id, weight_schema.HealthWeightUpdate(**changes), db, if_match=str(record.version)
        )

    def test_a_client_bmi_sent_with_a_weight_is_replaced_by_the_derived_one(self, db):
        record = _create(db)

        edited = self._edit(db, record, weight=80.0, bmi=5.0)

        assert edited.bmi == pytest.approx(80.0 / 1.75**2, abs=0.01)

    def test_a_client_bmi_sent_alone_is_ignored(self, db):
        record = _create(db)

        edited = self._edit(db, record, bmi=5.0)

        assert edited.bmi == pytest.approx(75.0 / 1.75**2, abs=0.01)

    @pytest.mark.parametrize("weight", [75.0, 70.3, 82.35])
    def test_an_edit_that_changes_nothing_keeps_the_version(self, db, weight):
        record = _create(db, weight=weight)

        edited = self._edit(db, record, weight=weight)

        assert edited.version == record.version

    def test_an_edit_of_the_date_keeps_the_stored_bmi(self, db):
        record = _create(db)

        edited = self._edit(db, record, date=date(2024, 1, 16))

        assert edited.bmi == pytest.approx(75.0 / 1.75**2, abs=0.01)


class TestProviderUpsert:
    def _upsert(self, db, bmi):
        record = weight_schema.HealthWeightCreate(date=_DAY, weight=75.0, bmi=bmi, source="garmin")
        return weight_integration.upsert_health_weight(1, record, db)

    def test_a_new_record_keeps_the_provider_bmi(self, db):
        assert self._upsert(db, 19.5).bmi == 19.5

    def test_an_updated_record_keeps_the_provider_bmi(self, db):
        self._upsert(db, 19.5)

        assert self._upsert(db, 20.5).bmi == 20.5

    def test_a_provider_record_without_a_bmi_gets_the_derived_one(self, db):
        assert self._upsert(db, None).bmi == pytest.approx(75.0 / 1.75**2, abs=0.01)
