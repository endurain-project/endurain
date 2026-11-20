"""``Idempotency-Key`` on the creates, against real PostgreSQL and the real routers.

A retry that carries the key of a create that already succeeded must not run the route again: the same ``201``,
``Location`` and ``ETag`` come back, and there is still one row, one audit row and one event. The keys are scoped to the
caller, whatever credential the caller used.
"""

import uuid
from collections.abc import Generator

import jasil.testing as jasil_testing
import pytest
from fastapi import FastAPI, Header, Request
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import core.database as core_database
import core.exceptions as core_exceptions
import core.idempotency as core_idempotency
import modules.auth.contracts as auth_contracts
import modules.auth.dependencies as auth_dependencies
import modules.followers.events as followers_events
import modules.followers.models as followers_models
import modules.followers.user_router as followers_user_router
import modules.gears.gear.router as gears_router
import modules.gears.gear_components.models as gear_components_models
import modules.gears.gear_components.router as gear_components_router
import modules.health.health_fasting.models as health_fasting_models
import modules.health.health_fasting.router as health_fasting_router
import modules.health.health_poop.models as health_poop_models
import modules.health.health_poop.router as health_poop_router
import modules.server_settings.models as server_settings_models
import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.models as users_models
import modules.users.users.router as users_router
from tests._helpers.db import ensure_user

_USER = uuid.UUID("00000000-0000-4000-8000-0000000000b1")
_OTHER = uuid.UUID("00000000-0000-4000-8000-0000000000b2")
_ADMIN = uuid.UUID("00000000-0000-4000-8000-0000000000b3")
_SCOPES = frozenset({"gears:write", "health:write", "followers:write", "users:write", "profile"})
_KEY = {"Idempotency-Key": '"create-0001"'}


def _principal(request: Request, x_user: str = Header(), x_credential: str = Header(default="session")):
    """Stand in for the credential check: who the caller is and how they signed in come from test headers."""
    credential = (
        auth_contracts.ApiKeyCred(api_key_id=uuid.uuid4(), key_prefix="abcd1234")
        if x_credential == "api_key"
        else auth_contracts.AccessTokenCred(session_id=uuid.uuid4())
    )
    principal = auth_contracts.Principal(
        user_id=uuid.UUID(x_user),
        username="user",
        email="user@example.com",
        is_active=True,
        is_superuser=False,
        scopes=_SCOPES,
        credential=credential,
    )
    request.state.principal = principal
    return principal


@pytest.fixture
def client(pg_factory) -> Generator[TestClient]:
    for user_id in (_USER, _OTHER, _ADMIN):
        ensure_user(pg_factory, user_id)
    with pg_factory() as db:
        db.add(server_settings_models.ServerSettings(id=1))
        db.commit()
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)
    app.include_router(gears_router.router, prefix="/gears")
    app.include_router(gear_components_router.router, prefix="/gear-components")
    app.include_router(health_poop_router.router, prefix="/health/poop")
    app.include_router(health_fasting_router.router, prefix="/health/fasting")
    app.include_router(followers_user_router.router, prefix="/users")
    app.include_router(users_router.router, prefix="/users")
    app.add_middleware(core_idempotency.IdempotencyMiddleware)

    def get_db() -> Generator:
        with pg_factory() as db:
            yield db

    app.dependency_overrides[core_database.get_db] = get_db
    app.dependency_overrides[auth_dependencies.get_principal] = _principal
    yield TestClient(app)


def _count(factory, model) -> int:
    with factory() as db:
        return db.scalar(select(func.count()).select_from(model)) or 0


def _as(user: uuid.UUID, credential: str = "session") -> dict[str, str]:
    return {**_KEY, "X-User": str(user), "X-Credential": credential}


def _same_response(first, second) -> None:
    assert second.status_code == first.status_code == 201
    assert second.content == first.content
    for header in ("Location", "ETag", "Content-Type"):
        assert second.headers.get(header) == first.headers.get(header)
        assert first.headers.get(header)


def test_a_repeated_poop_create_makes_one_row_and_answers_the_same(client, pg_factory):
    body = {"date_time": "2026-01-01T07:00:00Z"}

    first = client.post("/health/poop", json=body, headers=_as(_USER))
    second = client.post("/health/poop", json=body, headers=_as(_USER))

    _same_response(first, second)
    assert _count(pg_factory, health_poop_models.HealthPoop) == 1


def test_a_repeated_gear_component_create_makes_one_row_and_answers_the_same(client, pg_factory):
    gear = client.post("/gears", json={"nickname": "Road", "gear_type": "bike"}, headers=_as(_USER, "api_key"))
    assert gear.status_code == 201, gear.text
    body = {"gear_id": gear.json()["id"], "type": "back_tire", "brand": "Brand", "model": "Model"}
    headers = {**_as(_USER), "Idempotency-Key": '"component-0001"'}

    first = client.post("/gear-components", json=body, headers=headers)
    second = client.post("/gear-components", json=body, headers=headers)

    _same_response(first, second)
    assert _count(pg_factory, gear_components_models.GearComponents) == 1


def test_a_repeated_completed_fasting_create_makes_one_row_and_answers_the_same(client, pg_factory):
    body = {
        "fast_start_time": "2026-01-01T20:00:00Z",
        "fast_end_time": "2026-01-02T12:00:00Z",
        "status": "completed",
    }

    first = client.post("/health/fasting", json=body, headers=_as(_USER))
    second = client.post("/health/fasting", json=body, headers=_as(_USER))

    _same_response(first, second)
    assert _count(pg_factory, health_fasting_models.HealthFasting) == 1


def test_a_repeated_follow_publishes_one_event_and_makes_one_row(client, pg_factory, _platform):
    published: list = []
    _platform.events.subscribe(followers_events.FOLLOWER_REQUESTED, published.append)

    first = client.post(f"/users/{_OTHER}/followers", headers=_as(_USER))
    second = client.post(f"/users/{_OTHER}/followers", headers=_as(_USER))

    assert second.status_code == first.status_code == 201
    assert second.content == first.content
    assert _count(pg_factory, followers_models.Follower) == 1
    assert len(published) == 1


def test_a_repeated_user_create_writes_one_audit_row(client, pg_factory):
    body = {
        "name": "New User",
        "username": "newuser",
        "email": "new@example.com",
        "password": "Str0ng-Passw0rd!x",
        "access_type": "regular",
        "active": True,
    }

    with jasil_testing.capture_audit() as audit:
        first = client.post("/users", json=body, headers=_as(_ADMIN))
        second = client.post("/users", json=body, headers=_as(_ADMIN))

    assert first.status_code == second.status_code == 201, first.text + second.text
    assert second.content == first.content
    assert len(audit.matching(users_audit_actions.USER_CREATE.id)) == 1
    with pg_factory() as db:
        assert (
            db.scalar(
                select(func.count()).select_from(users_models.Users).where(users_models.Users.username == "newuser")
            )
            == 1
        )


def test_another_user_with_the_same_key_creates_their_own_row(client, pg_factory):
    body = {"date_time": "2026-01-01T07:00:00Z"}

    first = client.post("/health/poop", json=body, headers=_as(_USER))
    other = client.post("/health/poop", json=body, headers=_as(_OTHER))

    assert other.status_code == 201
    assert other.json()["id"] != first.json()["id"]
    assert _count(pg_factory, health_poop_models.HealthPoop) == 2


def test_a_session_and_an_api_key_of_one_user_share_their_keys(client, pg_factory):
    body = {"date_time": "2026-01-01T07:00:00Z"}

    by_session = client.post("/health/poop", json=body, headers=_as(_USER, "session"))
    by_key = client.post("/health/poop", json=body, headers=_as(_USER, "api_key"))

    _same_response(by_session, by_key)
    assert _count(pg_factory, health_poop_models.HealthPoop) == 1


def test_the_same_key_with_another_body_is_refused_and_creates_nothing(client, pg_factory):
    client.post("/health/poop", json={"date_time": "2026-01-01T07:00:00Z"}, headers=_as(_USER))

    other = client.post("/health/poop", json={"date_time": "2026-01-01T08:00:00Z"}, headers=_as(_USER))

    assert other.status_code == 422
    assert other.json()["type"] == "urn:endurain:error:idempotency-key-reused"
    assert _count(pg_factory, health_poop_models.HealthPoop) == 1


def test_a_refused_create_stores_nothing_and_leaves_the_key_free(client, pg_factory, _platform):
    refused = client.post(f"/users/{_USER}/followers", headers=_as(_USER))
    assert refused.status_code == 400

    assert list(_platform.state.iter_keys("endurain:idempotency:")) == []


@pytest.fixture
def _platform():
    import jasil.runtime as platform_runtime

    return platform_runtime.get_active_platform()
