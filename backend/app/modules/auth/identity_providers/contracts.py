"""Internal contracts for identity-provider persistence and OIDC flows."""

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

import modules.auth.identity_providers.constants as idp_constants
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.schema as auth_schema


class IdentityProviderState(BaseModel):
    """Stored provider configuration, including encrypted credentials."""

    id: int
    name: str
    slug: str
    provider_type: idp_constants.ProviderType
    enabled: bool
    client_id: str | None
    client_secret: str | None
    issuer_url: str | None
    authorization_endpoint: str | None
    token_endpoint: str | None
    userinfo_endpoint: str | None
    scopes: str | None
    icon: str | None
    icon_uploaded: bool
    auto_create_users: bool
    link_by_email: bool
    sync_user_info: bool
    sync_email: bool
    user_mapping: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    version: int

    model_config = ConfigDict(from_attributes=True, frozen=True)


class StagedBrowserFlow(BaseModel):
    """A link or step-up whose OAuth state is staged, waiting for the caller's commit before the provider URL.

    The provider URL may need OIDC discovery, a network call no open transaction may span, so the flow is staged,
    committed by the caller, and only then turned into a URL.

    Attributes:
        idp: The provider.
        purpose: The flow (``link`` or ``step_up``).
        state_id: The OAuth state id.
        nonce: The OIDC nonce.
        idp_code_verifier: The PKCE verifier whose challenge the provider URL carries.
        browser_binding: The secret the starting browser keeps in a cookie; the callback requires it.
    """

    idp: IdentityProviderState
    purpose: oauth_state_constants.OAuthStatePurpose
    state_id: str
    nonce: str
    idp_code_verifier: str
    browser_binding: str

    model_config = ConfigDict(frozen=True)


class EndSessionRequest(BaseModel):
    """What ending a session at its identity provider needs, read while the sign-in is still stored.

    The sign-in is deleted once the Endurain session ends, so the provider and the ID token are read first and the
    provider URL is built afterwards, with no database session open.

    Attributes:
        idp: The provider the session signed in through.
        encrypted_id_token: The ID token the provider issued at sign-in, encrypted; kept out of the repr.
    """

    idp: IdentityProviderState
    encrypted_id_token: str = Field(repr=False)

    model_config = ConfigDict(frozen=True)


class BrowserFlowStart(BaseModel):
    """Where to send the browser that starts a login, link or step-up, and the secret that binds the flow to it.

    Attributes:
        authorization_url: The provider's authorization URL.
        browser_binding: The secret the starting browser keeps in a cookie; the callback requires it.
    """

    authorization_url: str
    browser_binding: str

    model_config = ConfigDict(frozen=True)


class StepUpTicket(BaseModel):
    """What a fresh identity-provider sign-in proved, held until the sensitive request redeems it.

    Attributes:
        user_id: The signed-in user the provider account is linked to.
        session_id: The session that started the step-up.
        idp_id: The provider the user signed in with again.
        code_challenge: S256 challenge of the verifier the starting browser keeps; the redeeming request sends it.
        action: The sensitive operation the ticket pays for.
        security_generation: The account's security generation the step-up was started under; a ticket without one,
            or whose generation is no longer current, pays for nothing.
    """

    user_id: int
    session_id: str
    idp_id: int
    code_challenge: str
    action: str
    security_generation: int | None = None

    model_config = ConfigDict(frozen=True)


class StepUpVerifier(Protocol):
    """Verifies the step-up of the administrator making the request, for an operation this package administers.

    The identity-provider routes cannot verify a step-up themselves: that lives in ``account_security``, which
    depends on this package. The auth composition layer (``modules.auth.dependencies``) installs an implementation
    bound to the calling administrator's id and session, and the service calls it before it checks or writes
    anything.
    """

    def __call__(self, step_up: auth_schema.StepUpVerification, action: idp_constants.StepUpAction) -> None:
        """Verify the administrator's step-up for an action.

        Args:
            step_up: The step-up verification the administrator sent.
            action: The operation the step-up must authorise.

        Raises:
            StepUpFailedError: When the verification fails.
            IdpReauthRequiredError: When the administrator has no password and sent no identity-provider proof.
            TooManyRequestsError: When the administrator is locked out of step-up.
        """
        ...
