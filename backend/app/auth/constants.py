import os
from typing import Final

import core.config as core_config

# JWT config (typed + validated)
JWT_ALGORITHM: Final[str] = os.environ.get("ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES: Final[int] = int(
    os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 15)
)
JWT_REFRESH_TOKEN_EXPIRE_DAYS: Final[int] = int(
    os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", 7)
)
JWT_SECRET_KEY: Final[str | None] = core_config.read_secret("SECRET_KEY")
SESSION_IDLE_TIMEOUT_ENABLED: Final[bool] = (
    os.getenv("SESSION_IDLE_TIMEOUT_ENABLED", "false").lower() == "true"
)
SESSION_IDLE_TIMEOUT_HOURS: Final[int] = int(
    os.environ.get("SESSION_IDLE_TIMEOUT_HOURS", 1)
)
SESSION_ABSOLUTE_TIMEOUT_HOURS: Final[int] = int(
    os.environ.get("SESSION_ABSOLUTE_TIMEOUT_HOURS", 24)
)

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
ACTIVITIES_SCOPE: Final[tuple[str, ...]] = ("activities:read", "activities:write")
IDENTITY_PROVIDERS_REGULAR_SCOPE: Final[tuple[str, ...]] = ("identity_providers:read",)
IDENTITY_PROVIDERS_ADMIN_SCOPE: Final[tuple[str, ...]] = ("identity_providers:write",)
HEALTH_SCOPE: Final[tuple[str, ...]] = (
    "health:read",
    "health:write",
    "health_targets:read",
    "health_targets:write",
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
    "health:read": "Read privileges over health data",
    "health:write": "Write privileges over health data",
    "health_targets:read": "Read privileges over health targets data",
    "health_targets:write": "Write privileges over health targets data",
    "server_settings:read": "Read privileges over server settings",
    "server_settings:write": "Write privileges over server settings",
    "idp:read": "Read privileges over identity providers",
    "idp:write": "Write privileges over identity providers",
}

REGULAR_ACCESS_SCOPE: Final[tuple[str, ...]] = (
    USERS_REGULAR_SCOPE
    + GEARS_SCOPE
    + ACTIVITIES_SCOPE
    + HEALTH_SCOPE
    + SERVER_SETTINGS_REGULAR_SCOPE
    + IDENTITY_PROVIDERS_REGULAR_SCOPE
)
ADMIN_ACCESS_SCOPE: Final[tuple[str, ...]] = (
    REGULAR_ACCESS_SCOPE
    + USERS_ADMIN_SCOPE
    + IDENTITY_PROVIDERS_ADMIN_SCOPE
    + SERVER_SETTINGS_ADMIN_SCOPE
)
