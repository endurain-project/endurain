"""Principal type and credential discriminated union for auth boundary.

Defines the :class:`Principal` frozen dataclass that crosses the auth/users
boundary, plus the credential variant types that record *how* the principal
was authenticated.  Call sites must use :meth:`Principal.is_api_key` and
:meth:`Principal.credential_id` rather than pattern-matching on the
credential type directly.

Transaction contract: ``Principal`` is a pure value type; it carries no DB
session and performs no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

__all__ = [
    "AccessTokenCred",
    "AnyCredential",
    "ApiKeyCred",
    "OAuthCred",
    "PasswordCred",
    "Principal",
    "SessionCookieCred",
]


# ---------------------------------------------------------------------------
# Credential variants
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PasswordCred:
    """Credential issued after a username/password login.

    Attributes:
        username: The username that was authenticated.
    """

    username: str


@dataclass(frozen=True)
class AccessTokenCred:
    """Credential resolved from a JWT access token.

    Attributes:
        jti: JWT token identifier (``jti`` claim), if
            present.
        session_id: Session identifier (``sid`` claim).
        issued_at: Token issue time (``iat`` claim).
    """

    session_id: str
    jti: str | None = None
    issued_at: datetime | None = None


@dataclass(frozen=True)
class ApiKeyCred:
    """Credential resolved from an API key.

    Attributes:
        api_key_id: Database ID of the matching API
            key row.
        key_prefix: Human-readable prefix used in
            audit logs.
    """

    api_key_id: int
    key_prefix: str


@dataclass(frozen=True)
class SessionCookieCred:
    """Credential resolved from a session cookie.

    Attributes:
        session_id: The session identifier stored in
            the cookie.
    """

    session_id: str


@dataclass(frozen=True)
class OAuthCred:
    """Credential resolved after an OAuth callback.

    Attributes:
        provider: Identity provider name (e.g.
            ``"google"``, ``"github"``).
        external_id: Subject identifier returned by
            the provider.
    """

    provider: str
    external_id: str


#: Union of all credential variant types.
AnyCredential = PasswordCred | AccessTokenCred | ApiKeyCred | SessionCookieCred | OAuthCred


# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Principal:
    """Immutable identity token that crosses the auth/users boundary.

    ``Principal`` is the single value passed from the auth layer to the
    rest of the application. It carries the resolved identity and
    granted scopes, plus a typed credential that records *how*
    authentication succeeded.

    The resolved :attr:`Principal` should be cached on
    ``request.state.principal`` for the duration of the request so that
    multiple dependencies do not trigger duplicate DB lookups.

    Attributes:
        user_id: Authenticated user's primary key.
        username: Authenticated user's username.
        email: Authenticated user's e-mail address.
        is_active: Whether the account is currently
            active.
        is_superuser: Whether the account has
            superuser privileges.
        scopes: Immutable set of granted OAuth2
            scope strings.
        credential: Typed record of how this
            principal was authenticated.
    """

    user_id: int
    username: str
    email: str
    is_active: bool
    is_superuser: bool
    scopes: frozenset[str]
    credential: AnyCredential

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def is_api_key(self) -> bool:
        """Return ``True`` when authentication used an API key.

        Returns:
            bool: ``True`` if :attr:`credential` is an
                :class:`ApiKeyCred` instance, ``False`` otherwise.
        """
        return isinstance(self.credential, ApiKeyCred)

    def credential_id(self) -> str | int | None:
        """Return a stable identifier for the active credential.

        The returned value is suitable for audit logging and
        idempotency checks.  Its type depends on the credential
        variant:

        - :class:`AccessTokenCred` → ``session_id`` (str)
        - :class:`SessionCookieCred` → ``session_id`` (str)
        - :class:`ApiKeyCred` → ``api_key_id`` (int)
        - :class:`OAuthCred` → ``"<provider>:<external_id>"`` (str)
        - :class:`PasswordCred` → ``None``

        Returns:
            str | int | None: The credential identifier, or
                ``None`` when not applicable.
        """
        if isinstance(self.credential, AccessTokenCred):
            return self.credential.session_id
        if isinstance(self.credential, SessionCookieCred):
            return self.credential.session_id
        if isinstance(self.credential, ApiKeyCred):
            return self.credential.api_key_id
        if isinstance(self.credential, OAuthCred):
            return f"{self.credential.provider}:{self.credential.external_id}"
        return None
