import os

import core.config as core_config

# JWT Token constants
JWT_ALGORITHM = os.environ.get("ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "15")
)
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
JWT_SECRET_KEY = core_config.read_secret("SECRET_KEY")

# Scopes definition
USERS_REGULAR_SCOPES = ["profile", "users:read"]
USERS_ADMIN_SCOPES = ["users:write", "sessions:read", "sessions:write"]
GEARS_SCOPES = ["gears:read", "gears:write"]
ACTIVITIES_SCOPES = ["activities:read", "activities:write"]
HEALTH_SCOPES = [
    "health:read",
    "health:write",
    "health_targets:read",
    "health_targets:write",
]
SERVER_SETTINGS_REGULAR_SCOPES = []
SERVER_SETTINGS_ADMIN_SCOPES = ["server_settings:read", "server_settings:write"]
SCOPES_DICT = {
    "profile": "Privileges over user's own profile",
    "users:read": "Read privileges over users",
    "users:write": "Write privileges over users",
    "sessions:read": "Read privileges over sessions",
    "sessions:write": "Create/edit/delete privileges over sessions",
    "gears:read": "Read privileges over gears",
    "gears:write": "Write privileges over gears",
    "activities:read": "Read privileges over activities",
    "activities:write": "Write privileges over activities",
    "segments:read": "Read privileges over segments",
    "segments:write": "Write privileges over segments",
    "health:read": "Read privileges over health data",
    "health:write": "Write privileges over health data",
    "health_targets:read": "Read privileges over health targets data",
    "health_targets:write": "Write privileges over health targets data",
    "server_settings:read": "Read privileges over server settings",
    "server_settings:write": "Write privileges over server settings",
}

# Constants related to user access types
REGULAR_ACCESS_SCOPES = (
    USERS_REGULAR_SCOPES
    + GEARS_SCOPES
    + ACTIVITIES_SCOPES
    + HEALTH_SCOPES
    + SERVER_SETTINGS_REGULAR_SCOPES
)
ADMIN_ACCESS_SCOPES = (
    REGULAR_ACCESS_SCOPES + USERS_ADMIN_SCOPES + SERVER_SETTINGS_ADMIN_SCOPES
)
