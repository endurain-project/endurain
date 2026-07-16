"""Authentication constants.

Centralizes JWT configuration (algorithm, secret, token lifetimes), session
timeout settings, and the OAuth2 scope tuples consumed by
``internal_dependencies.py`` and ``token_manager.py``. All values are ``Final``
and validated at import time so misconfiguration fails fast at startup.
"""

import os
from typing import Final

import core.config as core_config

# JWT config (typed + validated)
# Allow-list of JWT signing algorithms accepted by the application. Pinned to
# HS256 only because:
#   1. The current key material is a symmetric ``OctKey`` (no asymmetric
#      keys are configured), so ``RS*``/``ES*``/``PS*`` and ``alg=none``
#      must never be accepted.
#   2. joserfc's default JWSRegistry treats ``HS384`` and ``HS512`` as
#      "not recommended" and refuses to encode or decode tokens signed
#      with them — adding either here would break token issuance, not
#      strengthen it. Enabling them would require constructing a custom
#      ``JWSRegistry`` and threading it through every encode/decode call.
# Extending this set therefore requires both a key-management change AND
# a joserfc registry change.
JWT_ALLOWED_ALGORITHMS: Final[frozenset[str]] = frozenset({"HS256"})
JWT_ALGORITHM: Final[str] = os.environ.get("ALGORITHM", "HS256")
if JWT_ALGORITHM not in JWT_ALLOWED_ALGORITHMS:
    raise ValueError(f"ALGORITHM={JWT_ALGORITHM!r} is not in the allow-list {sorted(JWT_ALLOWED_ALGORITHMS)}.")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES: Final[int] = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 15))
JWT_REFRESH_TOKEN_EXPIRE_DAYS: Final[int] = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", 7))
JWT_SECRET_KEY: Final[str | None] = core_config.read_secret("SECRET_KEY")
SESSION_IDLE_TIMEOUT_ENABLED: Final[bool] = os.getenv("SESSION_IDLE_TIMEOUT_ENABLED", "false").lower() == "true"
SESSION_IDLE_TIMEOUT_HOURS: Final[int] = int(os.environ.get("SESSION_IDLE_TIMEOUT_HOURS", 1))
SESSION_ABSOLUTE_TIMEOUT_HOURS: Final[int] = int(os.environ.get("SESSION_ABSOLUTE_TIMEOUT_HOURS", 24))

if JWT_ACCESS_TOKEN_EXPIRE_MINUTES <= 0:
    raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be positive")
if JWT_REFRESH_TOKEN_EXPIRE_DAYS <= 0:
    raise ValueError("REFRESH_TOKEN_EXPIRE_DAYS must be positive")
if not JWT_SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is required")

# scope (immutable)
USERS_REGULAR_SCOPE: Final[tuple[str, ...]] = ("profile", "users:read")
USERS_ADMIN_SCOPE: Final[tuple[str, ...]] = (
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
IDENTITY_PROVIDERS_REGULAR_SCOPE: Final[tuple[str, ...]] = ("identity_providers:read",)
IDENTITY_PROVIDERS_ADMIN_SCOPE: Final[tuple[str, ...]] = ("identity_providers:write",)
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
)

SCOPE_DICT: Final[dict[str, str]] = {
    "profile": "Privileges over user's own profile",
    "users:read": "Read privileges over users",
    "users:write": "Write privileges over users",
    "sessions:read": "Read privileges over sessions",
    "sessions:write": "Create/edit/delete privileges over sessions",
    "gears:read": "Read privileges over gears",
    "gears:write": "Write privileges over gears",
    "activities:read": "Read privileges over activities",
    "activities:write": "Write privileges over activities",
    "activities:upload": "Upload privileges over activities",
    "health:read": "Read privileges over health data",
    "health:write": "Write privileges over health data",
    "health_targets:read": "Read privileges over health targets data",
    "health_targets:write": "Write privileges over health targets data",
    "notifications:read": "Read privileges over notifications",
    "notifications:write": "Write privileges over notifications",
    "server_settings:read": "Read privileges over server settings",
    "server_settings:write": "Write privileges over server settings",
    "identity_providers:read": "Read privileges over identity providers",
    "identity_providers:write": "Write privileges over identity providers",
}

REGULAR_ACCESS_SCOPE: Final[tuple[str, ...]] = (
    USERS_REGULAR_SCOPE
    + ACTIVITIES_SCOPE
    + GEARS_SCOPE
    + IDENTITY_PROVIDERS_REGULAR_SCOPE
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
