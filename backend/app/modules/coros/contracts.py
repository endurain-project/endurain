"""COROS internal contracts shared by the OAuth, MCP and sync layers."""

from dataclasses import dataclass
from datetime import datetime


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
