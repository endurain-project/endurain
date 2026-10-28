"""Authentication scope constants."""

from typing import Final

# scope (immutable)
USERS_REGULAR_SCOPE: Final[tuple[str, ...]] = ("profile", "users:read")
USERS_ADMIN_SCOPE: Final[tuple[str, ...]] = (
    "users:read_all",
    "users:write",
    "sessions:read",
    "sessions:write",
)
GEARS_SCOPE: Final[tuple[str, ...]] = ("gears:read", "gears:write")
ACTIVITIES_SCOPE: Final[tuple[str, ...]] = (
    "activities:read",
    "activities:write",
    "activities:upload",
)
# The full provider configuration (client ids, endpoints, user mapping, disabled providers) is for administrators;
# regular users see the public listing instead.
IDENTITY_PROVIDERS_ADMIN_SCOPE: Final[tuple[str, ...]] = ("identity_providers:read", "identity_providers:write")
# The social graph gets its own scopes rather than riding the broad ``profile``
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
    "health_targets:read",
    "health_targets:write",
)
NOTIFICATIONS_REGULAR_SCOPE: Final[tuple[str, ...]] = (
    "notifications:read",
    "notifications:write",
)
SERVER_SETTINGS_REGULAR_SCOPE: Final[tuple[str, ...]] = ()
SERVER_SETTINGS_ADMIN_SCOPE: Final[tuple[str, ...]] = (
    "server_settings:read",
    "server_settings:write",
    "server_settings:logs",
    "server_settings:logs_clear",
)

SCOPE_DICT: Final[dict[str, str]] = {
    "profile": "Privileges over user's own profile",
    "users:read": "Read privileges over users",
    "users:read_all": "Read privileges over the full records of every user",
    "users:write": "Write privileges over users",
    "sessions:read": "Read privileges over sessions",
    "sessions:write": "Create/edit/delete privileges over sessions",
    "gears:read": "Read privileges over gears",
    "gears:write": "Write privileges over gears",
    "activities:read": "Read privileges over activities",
    "activities:write": "Write privileges over activities",
    "activities:upload": "Upload privileges over activities",
    "followers:read": "Read privileges over the follower/following graph",
    "followers:write": "Follow, unfollow, accept and remove followers",
    "health:read": "Read privileges over health data",
    "health:write": "Write privileges over health data",
    "health_targets:read": "Read privileges over health targets data",
    "health_targets:write": "Write privileges over health targets data",
    "notifications:read": "Read privileges over notifications",
    "notifications:write": "Write privileges over notifications",
    "server_settings:read": "Read privileges over server settings",
    "server_settings:write": "Write privileges over server settings",
    "server_settings:logs": "Read privileges over the server logs",
    "server_settings:logs_clear": "Privileges to clear the server logs",
    "identity_providers:read": "Read privileges over identity providers",
    "identity_providers:write": "Write privileges over identity providers",
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
# Swagger UI scope picker for OAuth2PasswordBearer) MUST be one that the
# server actually mints into a token, and every scope minted into a token
# MUST be advertised. A drift between the two surfaces means either:
#   - The UI offers a scope that is never enforced (false sense of
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
