"""A client never sets the provenance of a health record: the server assigns it."""

import importlib
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions

# kind -> (router prefix, valid create body, provenance fields a client must not send)
_KINDS = {
    "weight": ("health_weight", {"weight": 70.0}, {"source": "garmin"}),
    "steps": ("health_steps", {"steps": 100}, {"source": "garmin"}),
    "sleep": ("health_sleep", {}, {"source": "garmin"}),
    "water": ("health_water", {"amount_ml": 250}, {"source": "garmin"}),
    "poop": ("health_poop", {"date_time": "2026-01-01T07:00:00Z"}, {"source": "manual"}),
    "fasting": ("health_fasting", {"fast_start_time": "2026-01-01T07:00:00Z"}, {"source": "garmin"}),
}
_FIELDS = [
    (kind, field, value)
    for kind, (_, _, forged) in _KINDS.items()
    for field, value in {**forged, **({"garminconnect_sleep_id": "42"} if kind == "sleep" else {})}.items()
]
_HEADERS = {"Authorization": "Bearer x", "If-Match": '"1"'}


def _client(kind: str, mock_db) -> TestClient:
    import core.database as core_db
    import modules.auth.dependencies as auth_deps

    package = _KINDS[kind][0]
    router = importlib.import_module(f"modules.health.{package}.router")
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(router.router, prefix=f"/{package}")
    app.dependency_overrides[auth_deps.check_scopes] = lambda: None
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: 1
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return TestClient(app)


def _post(kind, body, mock_db):
    package = _KINDS[kind][0]
    with patch(f"modules.health.{package}.router.{package}_service"):
        return _client(kind, mock_db).post(f"/{package}", json=body, headers=_HEADERS)


def _patch(kind, body, mock_db):
    package = _KINDS[kind][0]
    with patch(f"modules.health.{package}.router.{package}_service"):
        return _client(kind, mock_db).patch(f"/{package}/1", json=body, headers=_HEADERS)


@pytest.mark.parametrize(("kind", "field", "value"), _FIELDS)
class TestClientCannotSetProvenance:
    def test_post_is_refused(self, kind, field, value, mock_db):
        body = _KINDS[kind][1]

        response = _post(kind, {**body, field: value}, mock_db)

        assert response.status_code == 422

    def test_patch_is_refused(self, kind, field, value, mock_db):
        response = _patch(kind, {field: value}, mock_db)

        assert response.status_code == 422


class TestServerAssignedSource:
    def test_a_client_poop_is_stored_as_manual(self, mock_db):
        import modules.health.health_poop.schema as schema
        import modules.health.health_poop.service as service

        with patch.object(service.health_poop_crud, "create_health_poop") as create:
            service.create_health_poop(1, schema.HealthPoopCreate(date_time="2026-01-01T07:00:00Z"), mock_db)

        assert create.call_args.args[1].source == "manual"

    def test_a_client_fasting_session_is_stored_as_manual(self, mock_db):
        import modules.health.health_fasting.schema as schema
        import modules.health.health_fasting.service as service

        with (
            patch.object(service.health_fasting_crud, "get_active_fasting_by_user_id", return_value=None),
            patch.object(service, "_overlaps", return_value=False),
            patch.object(service.health_fasting_crud, "create_health_fasting") as create,
        ):
            service.create_health_fasting(
                1, schema.HealthFastingCreate(fast_start_time="2026-01-01T07:00:00Z"), mock_db
            )

        assert create.call_args.args[1].source == "manual"

    @pytest.mark.parametrize(
        ("kind", "body"),
        [("weight", {"weight": 70.0}), ("steps", {"steps": 100}), ("sleep", {}), ("water", {"amount_ml": 250})],
    )
    def test_a_client_record_is_stored_without_a_source(self, kind, body, mock_db):
        crud = importlib.import_module(f"modules.health.health_{kind}.crud")
        schema = importlib.import_module(f"modules.health.health_{kind}.schema")
        create = getattr(schema, f"Health{kind.capitalize()}Create")

        with patch.object(crud.health_record_crud, "create") as stage:
            getattr(crud, f"create_health_{kind}")(1, create(date="2026-01-01", **body), mock_db)

        record = stage.call_args.args[2]
        assert record.model_dump().get("source") is None
        assert record.model_dump().get("garminconnect_sleep_id") is None
