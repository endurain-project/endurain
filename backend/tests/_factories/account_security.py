"""Step-up proofs, device sessions and the security-notice outbox, for the account-security tests."""

import base64
import hashlib
import uuid

import jasil.runtime as jasil_runtime
import jasil.testing as jasil_testing
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import core.hashing as core_hashing
import modules.auth.access_tokens.integration_service as access_tokens_integration
import modules.auth.account_security.subscribers as account_security_subscribers
import modules.auth.authentication.service as authentication_service
import modules.auth.constants as auth_constants
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.auth.identity_providers.contracts as identity_providers_contracts
import modules.auth.identity_providers.crud as identity_providers_crud
import modules.auth.identity_providers.schema as identity_providers_schema
import modules.auth.identity_providers.step_up_ticket_store as step_up_ticket_store
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.models as sessions_models
import modules.users.users.schema as users_schema
from tests._factories.auth import SignedIn

#: The PKCE verifier of every step-up ticket :func:`step_up_proof` issues.
CODE_VERIFIER = "v" * 43


def device_id_of(label: str) -> str:
    """Return a well-formed device id (43 URL-safe characters) for a label, so a test names its devices.

    Args:
        label: Anything unique to the device within the test.
    """
    return base64.urlsafe_b64encode(hashlib.sha256(label.encode()).digest()).decode().rstrip("=")


def sign_in_from_device(app: FastAPI, db: Session, user: users_schema.UserRead, device_id: str) -> SignedIn:
    """Sign a user in as a web client whose session records the device the id names.

    Sends the id as the ``X-Device-Id`` header too, as the mobile app does, so the request comes from that device.

    Args:
        app: The production application.
        db: Database session; the sign-in commits.
        user: The user to sign in.
        device_id: The id of the device the session signed in from.

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
        device_hash=core_hashing.sha256_hex(device_id),
    )
    assert outcome.refresh_cookie is not None
    headers = {
        "Authorization": f"Bearer {outcome.body.access_token}",
        "X-Client-Type": auth_constants.ClientType.WEB.value,
        "X-Device-Id": device_id,
    }
    return SignedIn(
        client=TestClient(app, headers=headers),
        user=user,
        session_id=outcome.body.session_id,
        access_token=outcome.body.access_token,
        refresh_token=outcome.refresh_cookie.value,
    )


def step_up_proof(
    db: Session,
    user: users_schema.UserRead,
    session_id: uuid.UUID,
    idp_id: uuid.UUID,
    action: identity_providers_constants.StepUpAction,
    *,
    verifier: str = CODE_VERIFIER,
) -> dict[str, str]:
    """Issue the ticket a fresh identity-provider sign-in leaves behind, and return the proof a request sends.

    The ticket goes into the platform state the application reads, under the account's current security generation.

    Args:
        db: Database session, which reads the generation.
        user: The user the provider account is linked to.
        session_id: The session that started the step-up.
        idp_id: The provider the user signed in with again.
        action: The operation the ticket pays for.
        verifier: The PKCE verifier whose challenge the ticket holds.

    Returns:
        The ``idp_reauth`` object of a step-up request.
    """
    challenge = base64.urlsafe_b64encode(hashlib.sha256(CODE_VERIFIER.encode()).digest()).decode().rstrip("=")
    ticket = step_up_ticket_store.StepUpTicketStore(jasil_runtime.get_active_platform().state).issue(
        identity_providers_contracts.StepUpTicket(
            user_id=user.id,
            session_id=session_id,
            idp_id=idp_id,
            code_challenge=challenge,
            action=action,
            security_generation=security_generation_integration.current_generation(user.id, db),
        )
    )
    return {"ticket": ticket, "code_verifier": verifier}


def deliver_notices() -> None:
    """Deliver the events the account-security routes publish to the notice subscribers, as the running server does."""
    account_security_subscribers.register_bus_subscribers(jasil_runtime.get_active_platform().events)


def outbox() -> list:
    """Return the messages the application has sent so far (the recording mail backend of the test platform)."""
    return jasil_testing.memory_mail(jasil_runtime.get_active_platform()).outbox


def session_ids(sessions: sessionmaker[Session], user_id: uuid.UUID) -> set[uuid.UUID]:
    """Read the ids of a user's sessions back in a new session.

    Args:
        sessions: The application's session factory (``committed_sessions``).
        user_id: The session owner.
    """
    with sessions() as db:
        return set(
            db.scalars(
                sa.select(sessions_models.UsersSessions.id).where(sessions_models.UsersSessions.user_id == user_id)
            )
        )


def sent_to(email: str) -> list:
    """Return the messages sent to an address so far, oldest first.

    Args:
        email: The recipient's address.
    """
    return [message for message in outbox() if any(email in recipient for recipient in message.to)]


def make_oidc_provider(db: Session, slug: str) -> uuid.UUID:
    """Stage an enabled OpenID Connect provider with explicit endpoints, so building its URL needs no discovery.

    A provider with an issuer is the kind an account without a password can sign in again with.

    Args:
        db: Database session; the provider is flushed, not committed.
        slug: The provider's slug, unique among providers.

    Returns:
        The provider's id.
    """
    created = identity_providers_crud.create_identity_provider(
        identity_providers_schema.IdentityProviderCreate(
            name=f"Provider {slug}",
            slug=slug,
            provider_type=identity_providers_constants.ProviderType.OIDC,
            enabled=True,
            issuer_url="https://idp.example.com",
            authorization_endpoint="https://idp.example.com/authorize",
            token_endpoint="https://idp.example.com/token",
            userinfo_endpoint="https://idp.example.com/userinfo",
            client_id="client-id",
            client_secret="client-secret",
        ),
        db,
    )
    return created.id
