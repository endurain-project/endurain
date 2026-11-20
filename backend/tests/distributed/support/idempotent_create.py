"""Act as an API replica: seed a user, or send one idempotent create through the real poop route.

Run from the ``app`` directory with the replica's environment. It builds the same platform the API does (Redis state
under the distributed profile), mounts the real health-poop router behind the idempotency middleware with a stand-in
for the credential check, waits for a shared start time, then posts the same create with the same ``Idempotency-Key``.
The route is slowed so that two replicas started together overlap. It prints ``RESULT <status> <body> <retry-after>``.

    idempotent_create.py seed
    idempotent_create.py post <user_id> <key> <start_at_epoch_seconds>
"""

# ruff: noqa: E402, T201 - a process entry point: it extends sys.path before importing, and prints for its parent.

import sys
import time
import uuid

sys.path.insert(0, ".")

import jasil.container as container
import jasil.lifecycle as lifecycle
import jasil.runtime as runtime
import jasil.settings as jasil_settings

import core.config as core_config
import core.platform_settings as core_platform_settings
import model_registry
import module_registry

model_registry.import_all_models()
substrate_settings = core_platform_settings.build_jasil_settings(
    core_config.settings, plain_areas=module_registry.storage_plain_areas()
)
jasil_settings.configure(substrate_settings)
platform = container.build_platform(substrate_settings)
runtime.set_active_platform(platform)
module_registry.configure_application()

import modules.users.users.models as users_models
from core.database import SessionLocal

#: How long the route lingers, so that a second replica's request arrives while the first is still running.
ROUTE_SECONDS = 4

if sys.argv[1] == "seed":
    with SessionLocal() as db:
        user = users_models.Users(
            name="Idempotent User",
            username="idempotent-user",
            email="idempotent-user@example.com",
            preferred_language="en",
            access_type="regular",
            timezone="UTC",
        )
        db.add(user)
        db.commit()
        print(f"USER {user.id}")
    lifecycle.shutdown()
    sys.exit(0)

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions
import core.idempotency as core_idempotency
import modules.auth.contracts as auth_contracts
import modules.auth.dependencies as auth_dependencies
import modules.health.health_poop.router as health_poop_router
import modules.health.health_poop.service as health_poop_service

user_id, key, start_at = uuid.UUID(sys.argv[2]), sys.argv[3], float(sys.argv[4])

create = health_poop_service.create_health_poop


def slow_create(*args, **kwargs):
    time.sleep(ROUTE_SECONDS)
    return create(*args, **kwargs)


health_poop_service.create_health_poop = slow_create


def principal(request: Request) -> auth_contracts.Principal:
    current = auth_contracts.Principal(
        user_id=user_id,
        username="idempotent-user",
        email="idempotent-user@example.com",
        is_active=True,
        is_superuser=False,
        scopes=frozenset({"health:write"}),
        credential=auth_contracts.AccessTokenCred(session_id=uuid.uuid4()),
    )
    request.state.principal = current
    return current


app = FastAPI()
core_exceptions.register_exception_handlers(app)
app.include_router(health_poop_router.router, prefix="/health/poop")
app.add_middleware(core_idempotency.IdempotencyMiddleware)
app.dependency_overrides[auth_dependencies.get_principal] = principal

client = TestClient(app)
while time.time() < start_at:
    time.sleep(0.01)
response = client.post("/health/poop", json={"date_time": "2026-01-01T07:00:00Z"}, headers={"Idempotency-Key": key})
print(f"RESULT {response.status_code} {response.text} {response.headers.get('Retry-After', '-')}")
lifecycle.shutdown()
