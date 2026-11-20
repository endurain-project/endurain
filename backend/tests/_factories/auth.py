"""Signed-in clients of the production application, for tests on the real database."""

import uuid
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.authentication.service as authentication_service
import modules.auth.constants as auth_constants
import modules.auth.security_generation.integration_service as security_generation_integration
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
