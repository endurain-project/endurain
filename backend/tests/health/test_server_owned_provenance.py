"""A client never sets the provenance of a health record: the server assigns it."""

import uuid

import pytest
import sqlalchemy as sa

import core.config as core_config
import modules.health.health_fasting.models as fasting_models
import modules.health.health_poop.models as poop_models
import modules.health.health_sleep.models as sleep_models
import modules.health.health_steps.models as steps_models
import modules.health.health_water.models as water_models
import modules.health.health_weight.models as weight_models
from tests._factories import health as health_factories
from tests._factories.users import make_user

_URL = f"{core_config.ROOT_PATH}/health"

# kind -> (valid create body, provenance fields a client must not send, model, record maker)
_KINDS = {
    "weight": (
        {"weight_kg": 70.0},
        {"source": "garmin"},
        weight_models.HealthWeight,
        health_factories.make_health_weight,
    ),
    "steps": ({"steps": 100}, {"source": "garmin"}, steps_models.HealthSteps, health_factories.make_health_steps),
    "sleep": (
        {},
        {"source": "garmin", "garminconnect_sleep_id": "42"},
        sleep_models.HealthSleep,
        health_factories.make_health_sleep,
    ),
    "water": ({"amount_ml": 250}, {"source": "garmin"}, water_models.HealthWater, health_factories.make_health_water),
    "poop": (
        {"date_time": "2025-01-01T07:00:00Z"},
        {"source": "manual"},
        poop_models.HealthPoop,
        health_factories.make_health_poop,
    ),
    "fasting": (
        {"fast_start_time": "2025-01-01T07:00:00Z"},
        {"source": "garmin"},
        fasting_models.HealthFasting,
        health_factories.make_health_fasting,
    ),
}
_FIELDS = [
    pytest.param(kind, field, value, id=f"{kind}-{field}")
    for kind, (_, forged, _, _) in _KINDS.items()
    for field, value in forged.items()
]
_DATED = {"weight", "steps", "sleep", "water"}


def _body(kind: str) -> dict:
    """The valid create body of a kind, dated where the kind has a day."""
    body = dict(_KINDS[kind][0])
    return {"date": "2025-01-01", **body} if kind in _DATED else body


@pytest.fixture
def user(committed_sessions):
    with committed_sessions() as db:
        created = make_user(db, timezone="UTC")
        db.commit()
    return created


@pytest.fixture
def me(sign_in, user):
    return sign_in(user)


def _count(committed_sessions, model) -> int:
    with committed_sessions() as db:
        return db.scalar(sa.select(sa.func.count()).select_from(model))


@pytest.mark.parametrize(("kind", "field", "value"), _FIELDS)
class TestClientCannotSetProvenance:
    def test_a_create_is_refused_and_stores_nothing(self, me, committed_sessions, kind, field, value):
        response = me.client.post(f"{_URL}/{kind}", json={**_body(kind), field: value})

        assert response.status_code == 422
        assert _count(committed_sessions, _KINDS[kind][2]) == 0

    def test_an_edit_is_refused(self, me, user, committed_sessions, kind, field, value):
        with committed_sessions() as db:
            record = _KINDS[kind][3](db, user.id)
            db.commit()

        response = me.client.patch(f"{_URL}/{kind}/{record.id}", json={field: value}, headers={"If-Match": '"1"'})

        assert response.status_code == 422
        with committed_sessions() as db:
            assert db.get(_KINDS[kind][2], record.id).version == 1


class TestServerAssignedSource:
    @pytest.mark.parametrize("kind", list(_KINDS))
    def test_a_client_record_is_stored_as_manual(self, me, committed_sessions, kind):
        response = me.client.post(f"{_URL}/{kind}", json=_body(kind))

        assert response.status_code == 201
        assert response.json()["source"] == "manual"
        with committed_sessions() as db:
            row = db.get(_KINDS[kind][2], uuid.UUID(response.json()["id"]))
            assert row.source == "manual"
            assert getattr(row, "garminconnect_sleep_id", None) is None
