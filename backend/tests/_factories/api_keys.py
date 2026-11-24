"""API keys and clients that call the production application with one, for tests on the real database."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.integration_service as api_keys_integration
import modules.auth.api_keys.schema as api_keys_schema
import modules.users.users.schema as users_schema


@dataclass(frozen=True)
class KeyHolder:
    """A client that sends one API key with every request.

    Attributes:
        client: Sends the key in ``X-API-Key``.
        user: The key's owner.
        key: The stored key.
        raw_key: The key's secret value, shown once at creation.
    """

    client: TestClient
    user: users_schema.UserRead
    key: api_keys_schema.UserApiKeyRead
    raw_key: str


def make_api_key(
    db: Session,
    user: users_schema.UserRead,
    *,
    scopes: list[api_keys_constants.ApiKeyScope],
    expires_at: datetime | None = None,
    name: str = "test key",
) -> tuple[api_keys_schema.UserApiKeyRead, str]:
    """Stage an API key through the module's create path.

    The step-up the route demands before it creates a key is the route's concern, so the request schema is built
    without one.

    Args:
        db: Database session; the key is flushed, not committed.
        user: The key's owner.
        scopes: The scopes the key holds.
        expires_at: When the key expires; 30 days from now when omitted.
        name: The key's label.

    Returns:
        The stored key and its secret value.
    """
    raw_key = api_keys_integration.generate_api_key()
    request = api_keys_schema.UserApiKeyCreate.model_construct(name=name, scopes=scopes)
    key = api_keys_integration.create_api_key(
        user.id, request, raw_key, expires_at or datetime.now(UTC) + timedelta(days=30), db
    )
    return key, raw_key


def key_client(
    app: FastAPI, user: users_schema.UserRead, key: api_keys_schema.UserApiKeyRead, raw_key: str
) -> KeyHolder:
    """Return a client of the production application that authenticates with an API key.

    Args:
        app: The production application.
        user: The key's owner.
        key: The stored key.
        raw_key: The key's secret value.

    Returns:
        The client and the key it sends.
    """
    return KeyHolder(client=TestClient(app, headers={"X-API-Key": raw_key}), user=user, key=key, raw_key=raw_key)
