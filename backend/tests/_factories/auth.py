"""Signed-in clients of the production application, for tests on the real database."""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.service as authentication_service
import modules.auth.constants as auth_constants
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.contracts as sessions_contracts
import modules.auth.sessions.crud as sessions_crud
import modules.auth.sessions.models as sessions_models
import modules.auth.sessions.service as sessions_service
import modules.users.users.schema as users_schema


@dataclass(frozen=True)
class SignedIn:
    """A web client signed in as a user.

    Attributes:
        client: Sends the user's access token and the web client type with every request.
        user: Who is signed in.
        session_id: The session the sign-in created.
        access_token: The bearer access token.
        refresh_token: The refresh token the web client holds as a cookie.
    """

    client: TestClient
    user: users_schema.UserRead
    session_id: uuid.UUID
    access_token: str
    refresh_token: str


def sign_in(app: FastAPI, db: Session, user: users_schema.UserRead) -> SignedIn:
    """Sign a user in as a web client, through the step a password sign-in completes with.

    The session row and the tokens are the real ones: only the password check before it is skipped. The step commits,
    as a sign-in does.

    Args:
        app: The production application.
        db: Database session.
        user: The user to sign in.

    Returns:
        The signed-in client.
    """
    outcome = authentication_service.complete_login(
        "testclient",
        "pytest",
        user,
        access_tokens_integration.get_token_manager(),
        db,
        mfa=False,
        security_generation=security_generation_integration.current_generation(user.id, db),
        device_hash=None,
    )
    assert outcome.refresh_cookie is not None
    headers = {
        "Authorization": f"Bearer {outcome.body.access_token}",
        "X-Client-Type": auth_constants.ClientType.WEB.value,
    }
    return SignedIn(
        client=TestClient(app, headers=headers),
        user=user,
        session_id=outcome.body.session_id,
        access_token=outcome.body.access_token,
        refresh_token=outcome.refresh_cookie.value,
    )


def make_session(
    db: Session,
    user: users_schema.UserRead,
    *,
    client_type: auth_constants.ClientType = auth_constants.ClientType.WEB,
    exchanged: bool = True,
    refresh_token: str | None = None,
    expires_at: datetime | None = None,
    created_at: datetime | None = None,
    last_activity_at: datetime | None = None,
    oauth_state_id: str | None = None,
    device_hash: str | None = None,
) -> sessions_contracts.SessionRead:
    """Stage a session through the module's create path, as a sign-in does (flushed, not committed).

    Args:
        db: Database session.
        user: The session's owner.
        client_type: The client type the session was created for.
        exchanged: Whether the session holds a refresh token; false for the session of a sign-in that awaits its
            token exchange.
        refresh_token: The raw refresh token to digest; a random one when omitted and ``exchanged``.
        expires_at: When the session expires; seven days from now when omitted.
        created_at: Rewrites the creation time afterwards, for a session that is already old.
        last_activity_at: Rewrites the last activity afterwards, for a session that has been idle.
        oauth_state_id: The OAuth state the session waits on.
        device_hash: The known device the session signed in from.

    Returns:
        The session as stored.
    """
    session_id = uuid.uuid4()
    token = (refresh_token or secrets.token_urlsafe(32)) if exchanged else None
    sessions_service.create_session(
        session_id,
        user,
        client_type,
        "127.0.0.1",
        "pytest",
        token,
        expires_at or datetime.now(UTC) + timedelta(days=7),
        db,
        oauth_state_id,
        amr=["pwd"],
        device_hash=device_hash,
    )
    rewrites = {
        name: value
        for name, value in (("created_at", created_at), ("last_activity_at", last_activity_at))
        if value is not None
    }
    if rewrites:
        db.execute(
            sa.update(sessions_models.UsersSessions)
            .where(sessions_models.UsersSessions.id == session_id)
            .values(**rewrites)
        )
        db.flush()
    stored = sessions_crud.get_session_by_id(session_id, db)
    assert stored is not None
    return stored
