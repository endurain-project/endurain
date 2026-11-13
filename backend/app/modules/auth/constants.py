"""Authentication constants: client types and scopes."""

from enum import StrEnum
from typing import Final


class ClientType(StrEnum):
    """Client kinds that sign in, as named by the ``X-Client-Type`` header."""

    WEB = "web"
    MOBILE = "mobile"


class MFAFactorType(StrEnum):
    """Kinds of second factor a user can enrol in ``mfa_factors``; backup codes are stored apart."""

    TOTP = "totp"


class AuthMethod(StrEnum):
    """Authentication methods a session records in its ``amr``.

    ``pwd``, ``otp`` and ``mfa`` are RFC 8176 values. ``fed`` is not in the RFC 8176 registry: it is a de-facto value,
    the one Microsoft Entra ID emits for a federated sign-in.
    """

    LOCAL_CREDENTIAL = "pwd"  # the account's own password
    FEDERATED = "fed"
    ONE_TIME_CODE = "otp"  # a TOTP or backup code
    MULTI_FACTOR = "mfa"  # more than one factor was used


#: The requests an account that must enrol MFA but has not may still make, as ``(method, route template)`` below the
#: API root. They are what the web app's enrolment page needs and nothing more: the account itself (to show who is
#: signed in), the MFA status, the setup and enable calls that enrol it, and, for an account without a local
#: password, the linked identity providers and the identity-provider step-up that enable call asks for. Signing out
#: is not an authenticated request and needs no exemption.
MFA_ENROLMENT_ROUTES: Final[frozenset[tuple[str, str]]] = frozenset(
    {
        ("GET", "/profile"),
        ("GET", "/profile/mfa/status"),
        ("POST", "/profile/mfa/setup"),
        ("POST", "/profile/mfa/enable"),
        ("GET", "/profile/identity-providers"),
        ("POST", "/profile/identity-providers/{idp_id}/step-up"),
    }
)

# scope (immutable)
# ``account`` covers the account's own data (profile, photo, goals, privacy, default gear). Three narrower scopes
# split off what an integration token should not hold by default: taking the account's data out or in
# (``account:export``), changing how the account is protected or closing it (``account:security``), and linking or
# unlinking a Garmin Connect or Strava account, which hands the provider's credentials to the server
# (``account:integrations``).
USERS_REGULAR_SCOPE: Final[tuple[str, ...]] = (
    "account",
    "account:export",
    "account:security",
    "account:integrations",
    "users:read",
)
USERS_ADMIN_SCOPE: Final[tuple[str, ...]] = (
    "users:read-all",
    "users:write",
    "sessions:read",
    "sessions:write",
    "api-keys:read",
    "api-keys:write",
)
GEARS_SCOPE: Final[tuple[str, ...]] = ("gears:read", "gears:write")
ACTIVITIES_SCOPE: Final[tuple[str, ...]] = (
    "activities:read",
    "activities:write",
    "activities:upload",
)
# The full provider configuration (client ids, endpoints, user mapping, disabled providers) is for administrators;
# regular users see the public listing instead.
IDENTITY_PROVIDERS_ADMIN_SCOPE: Final[tuple[str, ...]] = ("identity-providers:read", "identity-providers:write")
# The social graph gets its own scopes rather than riding the broad ``account``
# scope: following/unfollowing is a distinct, externally visible action, and an
# integration token issued to edit a profile should not silently be able to
# rearrange who the user follows (least privilege, OWASP A01).
FOLLOWERS_SCOPE: Final[tuple[str, ...]] = (
    "followers:read",
    "followers:write",
)
HEALTH_SCOPE: Final[tuple[str, ...]] = (
    "health:read",
    "health:write",
    "health-targets:read",
    "health-targets:write",
)
NOTIFICATIONS_REGULAR_SCOPE: Final[tuple[str, ...]] = (
    "notifications:read",
    "notifications:write",
)
SERVER_SETTINGS_REGULAR_SCOPE: Final[tuple[str, ...]] = ()
SERVER_SETTINGS_ADMIN_SCOPE: Final[tuple[str, ...]] = (
    "server-settings:read",
    "server-settings:write",
    "server-settings:logs",
    "server-settings:logs-clear",
)

SCOPE_DICT: Final[dict[str, str]] = {
    "account": "Privileges over user's own account data",
    "account:export": "Export and import the user's own account data",
    "account:security": (
        "Change the user's own password, email, MFA, API keys, sessions and identity links, and delete the account"
    ),
    "account:integrations": "Link and unlink the user's own Garmin Connect and Strava accounts",
    "users:read": "Read privileges over users",
    "users:read-all": "Read privileges over the full records of every user",
    "users:write": "Write privileges over users",
    "sessions:read": "Read privileges over sessions",
    "sessions:write": "Create/edit/delete privileges over sessions",
    "api-keys:read": "Read privileges over the API keys of every user",
    "api-keys:write": "Revoke privileges over the API keys of every user",
    "gears:read": "Read privileges over gears",
    "gears:write": "Write privileges over gears",
    "activities:read": "Read privileges over activities",
    "activities:write": "Write privileges over activities",
    "activities:upload": "Upload privileges over activities",
    "followers:read": "Read privileges over the follower/following graph",
    "followers:write": "Follow, unfollow, accept and remove followers",
    "health:read": "Read privileges over health data",
    "health:write": "Write privileges over health data",
    "health-targets:read": "Read privileges over health targets data",
    "health-targets:write": "Write privileges over health targets data",
    "notifications:read": "Read privileges over notifications",
    "notifications:write": "Write privileges over notifications",
    "server-settings:read": "Read privileges over server settings",
    "server-settings:write": "Write privileges over server settings",
    "server-settings:logs": "Read privileges over the server logs",
    "server-settings:logs-clear": "Privileges to clear the server logs",
    "identity-providers:read": "Read privileges over identity providers",
    "identity-providers:write": "Write privileges over identity providers",
}

REGULAR_ACCESS_SCOPE: Final[tuple[str, ...]] = (
    USERS_REGULAR_SCOPE
    + ACTIVITIES_SCOPE
    + FOLLOWERS_SCOPE
    + GEARS_SCOPE
    + HEALTH_SCOPE
    + NOTIFICATIONS_REGULAR_SCOPE
    + SERVER_SETTINGS_REGULAR_SCOPE
)
ADMIN_ACCESS_SCOPE: Final[tuple[str, ...]] = (
    REGULAR_ACCESS_SCOPE + USERS_ADMIN_SCOPE + IDENTITY_PROVIDERS_ADMIN_SCOPE + SERVER_SETTINGS_ADMIN_SCOPE
)

# Startup invariant: every scope advertised in SCOPE_DICT (which feeds the
# scope catalogue in the HTTPBearer scheme's OpenAPI description) MUST be one that the
# server actually mints into a token, and every scope minted into a token
# MUST be advertised. A drift between the two surfaces means either:
#   - The docs offer a scope that is never enforced (false sense of
#     authorisation granularity — the original `idp:read`/`idp:write` bug).
#   - A token carries a scope that the OpenAPI doc never describes
#     (silent privilege, harder to audit).
# Failing fast at import keeps the two in lockstep.
_ALL_MINTED_SCOPES: Final[frozenset[str]] = frozenset(ADMIN_ACCESS_SCOPE)
_ADVERTISED_SCOPES: Final[frozenset[str]] = frozenset(SCOPE_DICT)
_unadvertised = _ALL_MINTED_SCOPES - _ADVERTISED_SCOPES
_unminted = _ADVERTISED_SCOPES - _ALL_MINTED_SCOPES
if _unadvertised or _unminted:
    raise ValueError(
        "SCOPE_DICT is out of sync with the scope tuples: "
        f"minted-but-undeclared={sorted(_unadvertised)}, "
        f"declared-but-never-minted={sorted(_unminted)}"
    )
