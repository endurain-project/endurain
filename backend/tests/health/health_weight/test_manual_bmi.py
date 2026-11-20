"""The BMI of a weight record: derived from the user's height for a manual one, kept for a provider's."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from tests._factories.health import make_health_weight
from tests._factories.users import make_user

import core.etag as core_etag
import modules.health.health_weight.integration_service as health_weight_integration
import modules.health.health_weight.models as health_weight_models
import modules.health.health_weight.schema as health_weight_schema
import modules.health.health_weight.service as health_weight_service

_DAY = date(2024, 1, 15)
_BMI_75_AT_175 = pytest.approx(75.0 / 1.75**2, abs=0.01)


def _bmi(db, record_id) -> Decimal | None:
    db.expire_all()
    return db.get(health_weight_models.HealthWeight, record_id).bmi


def _create(db, user, *, bmi=None, weight=75.0, day=_DAY):
    return health_weight_service.create_health_weight(
        user.id, health_weight_schema.HealthWeightCreate(date=day, weight_kg=weight, bmi=bmi), db
    )


def _edit(db, user, record, **changes):
    return health_weight_service.edit_health_weight(
        user.id,
        record.id,
        health_weight_schema.HealthWeightUpdate(**changes),
        db,
        if_match=core_etag.format_etag(record.version),
    )


@pytest.fixture
def user(db):
    return make_user(db, timezone="UTC", height=175)


class TestManualCreate:
    def test_a_client_bmi_is_replaced_by_the_derived_one(self, db, user):
        stored = _create(db, user, bmi=5.0)

        assert stored.bmi == _BMI_75_AT_175
        assert float(_bmi(db, stored.id)) == _BMI_75_AT_175

    def test_the_bmi_is_derived_when_none_is_sent(self, db, user):
        assert _create(db, user).bmi == _BMI_75_AT_175

    def test_without_a_height_the_bmi_is_empty_whatever_the_client_sent(self, db):
        no_height = make_user(db, timezone="UTC")

        assert _create(db, no_height, bmi=22.0).bmi is None

    def test_a_result_above_the_largest_bmi_is_not_stored(self, db):
        tiny = make_user(db, timezone="UTC", height=5)

        assert _create(db, tiny).bmi is None


class TestManualEdit:
    def test_a_client_bmi_sent_with_a_weight_is_replaced_by_the_derived_one(self, db, user):
        record = _create(db, user)

        edited = _edit(db, user, record, weight_kg=80.0, bmi=5.0)

        assert edited.bmi == pytest.approx(80.0 / 1.75**2, abs=0.01)

    def test_a_client_bmi_sent_alone_is_ignored(self, db, user):
        record = _create(db, user)

        edited = _edit(db, user, record, bmi=5.0)

        assert edited.bmi == _BMI_75_AT_175

    @pytest.mark.parametrize("weight", [75.0, 70.3, 82.35])
    def test_an_edit_that_changes_nothing_keeps_the_version(self, db, user, weight):
        record = _create(db, user, weight=weight)

        assert _edit(db, user, record, weight_kg=weight).version == record.version

    def test_an_edit_of_the_date_keeps_the_stored_bmi(self, db, user):
        record = _create(db, user)

        edited = _edit(db, user, record, date=_DAY + timedelta(days=1))

        assert edited.bmi == _BMI_75_AT_175


class TestProviderUpsert:
    def _upsert(self, db, user, bmi):
        record = health_weight_schema.HealthWeightImport(date=_DAY, weight_kg=75.0, bmi=bmi, source="garmin")
        return health_weight_integration.upsert_health_weight(user.id, record, db)

    def test_a_new_record_keeps_the_provider_bmi(self, db, user):
        assert self._upsert(db, user, 19.5).bmi == 19.5

    def test_an_updated_record_keeps_the_provider_bmi(self, db, user):
        self._upsert(db, user, 19.5)

        assert self._upsert(db, user, 20.5).bmi == 20.5

    def test_a_provider_record_without_a_bmi_gets_the_derived_one(self, db, user):
        assert self._upsert(db, user, None).bmi == _BMI_75_AT_175


class TestRecalculateOnAHeightChange:
    def test_a_manual_record_follows_the_new_height_and_its_version_moves_on(self, db, user):
        record = make_health_weight(db, user.id, date=_DAY, weight_kg=70.5, bmi=1.0)

        health_weight_integration.recalculate_bmi_for_user(user.id, 178.0, db)

        db.expire_all()
        row = db.get(health_weight_models.HealthWeight, record.id)
        assert (row.bmi, row.version) == (Decimal("22.25"), record.version + 1)

    def test_a_provider_record_keeps_the_bmi_it_reported_whatever_the_height(self, db, user):
        record = make_health_weight(db, user.id, date=_DAY, weight_kg=70.0, bmi=19.5, source="garmin")

        health_weight_integration.recalculate_bmi_for_user(user.id, 175.0, db)
        assert _bmi(db, record.id) == Decimal("19.50")

        health_weight_integration.recalculate_bmi_for_user(user.id, None, db)
        assert _bmi(db, record.id) == Decimal("19.50")

    @pytest.mark.parametrize("height", [None, 0.0])
    def test_without_a_usable_height_a_manual_bmi_is_cleared(self, db, user, height):
        record = make_health_weight(db, user.id, date=_DAY, weight_kg=70.0, bmi=22.0)

        health_weight_integration.recalculate_bmi_for_user(user.id, height, db)

        assert _bmi(db, record.id) is None

    @pytest.mark.parametrize("height", [5.0, 70.0])
    def test_a_result_above_the_largest_bmi_is_cleared_without_an_error(self, db, user, height):
        record = make_health_weight(db, user.id, date=_DAY, weight_kg=70.5, bmi=20.0)

        health_weight_integration.recalculate_bmi_for_user(user.id, height, db)

        assert _bmi(db, record.id) is None

    def test_another_users_records_are_not_touched(self, db, user):
        other = make_user(db)
        theirs = make_health_weight(db, other.id, date=_DAY, weight_kg=70.0, bmi=22.0)

        health_weight_integration.recalculate_bmi_for_user(user.id, 175.0, db)

        db.expire_all()
        row = db.get(health_weight_models.HealthWeight, theirs.id)
        assert (row.bmi, row.version) == (Decimal("22.00"), 1)
