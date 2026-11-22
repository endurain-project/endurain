"""COROS internal contracts shared by the OAuth, MCP and sync layers."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from modules.coros.constants import SyncErrorCode, SyncStatus


@dataclass(frozen=True)
class CorosOAuthMetadata:
    """Authorization-server metadata discovered from COROS.

    Attributes:
        issuer: OAuth issuer.
        authorization_endpoint: Browser authorization endpoint.
        token_endpoint: Code exchange and refresh endpoint.
        revocation_endpoint: Token revocation endpoint, when published.
        registration_endpoint: Dynamic client registration endpoint.
        mcp_url: Protected MCP resource the access token is meant for.
        scopes: Scopes the server publishes.
    """

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    revocation_endpoint: str | None
    registration_endpoint: str | None
    mcp_url: str
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class CorosClientRegistration:
    """A public OAuth client registered through COROS dynamic registration.

    Attributes:
        client_id: Registered client identifier.
        client_secret: Secret when the server issues one, otherwise None.
    """

    client_id: str
    client_secret: str | None = None


@dataclass(frozen=True)
class CorosTokenSet:
    """Tokens returned by the COROS token endpoint.

    Attributes:
        access_token: Bearer token for the MCP endpoint.
        refresh_token: Rotating refresh token.
        token_expires_at: Access-token expiry.
        refresh_token_expires_at: Refresh-token expiry.
        scope: Granted scopes.
    """

    access_token: str
    refresh_token: str
    token_expires_at: datetime
    refresh_token_expires_at: datetime
    scope: str


@dataclass(frozen=True)
class CorosActivitySummary:
    """One activity row parsed from ``querySportRecords``.

    Attributes:
        label_id: COROS activity identifier used by the detail and FIT tools.
        sport_type: COROS numeric sport code required alongside ``label_id``.
    """

    label_id: str
    sport_type: int


class CorosIntegrationData(BaseModel):
    """Internal row view used by the service layer.

    Tokens are already decrypted by CRUD. This model never reaches a client.

    Attributes:
        id: Row id.
        user_id: Owning user id.
        mcp_url: Regional MCP endpoint.
        issuer: OAuth issuer.
        redirect_uri: Registered callback URI.
        scope: Granted scopes.
        client_id: Public OAuth client id.
        client_secret: Decrypted client secret, when issued.
        state: Pending OAuth state.
        code_verifier: Decrypted PKCE verifier.
        state_expires_at: Pending state expiry.
        access_token: Decrypted access token.
        refresh_token: Decrypted refresh token.
        token_expires_at: Access-token expiry.
        refresh_token_expires_at: Refresh-token expiry.
        last_sync_at: Last sync attempt time.
        last_sync_status: Last sync outcome.
        last_sync_error: Sanitized failure code.
        last_sync_activity_count: Activities stored by the last successful sync.
        fit_download_date: UTC date of the FIT download counter.
        fit_download_count: FIT downloads spent on that date.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    mcp_url: str | None = None
    issuer: str | None = None
    redirect_uri: str | None = None
    scope: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    state: str | None = None
    code_verifier: str | None = None
    state_expires_at: datetime | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_expires_at: datetime | None = None
    refresh_token_expires_at: datetime | None = None
    last_sync_at: datetime | None = None
    last_sync_status: SyncStatus = SyncStatus.NEVER
    last_sync_error: SyncErrorCode | None = None
    last_sync_activity_count: int = 0
    fit_download_date: date | None = None
    fit_download_count: int = 0
