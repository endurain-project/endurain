"""Internal contracts for identity-provider persistence and OIDC flows."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

import modules.auth.oauth_state.constants as oauth_state_constants


class IdentityProviderState(BaseModel):
    """Stored provider configuration, including encrypted credentials."""

    id: int
    name: str
    slug: str
    provider_type: str
    enabled: bool
    client_id: str | None
    client_secret: str | None
    issuer_url: str | None
    authorization_endpoint: str | None
    token_endpoint: str | None
    userinfo_endpoint: str | None
    jwks_uri: str | None
    scopes: str | None
    icon: str | None
    icon_uploaded: bool
    auto_create_users: bool
    sync_user_info: bool
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


class BrowserFlowStart(BaseModel):
    """Where to send the browser that starts a link or step-up, and the secret that binds the flow to it.

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
    """

    user_id: int
    session_id: str
    idp_id: int
    code_challenge: str
    action: str

    model_config = ConfigDict(frozen=True)
