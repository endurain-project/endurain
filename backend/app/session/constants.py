import os

# JWT Token constants
JWT_ALGORITHM = os.environ.get("ALGORITHM")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES"))
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS"))
JWT_SECRET_KEY = os.environ.get("SECRET_KEY")

# Scopes definition
USERS_REGULAR_SCOPES = ["profile", "users:read"]
USERS_ADMIN_SCOPES = ["users:write"]
GEARS_SCOPES = ["gears:read", "gears:write"]
ACTIVITIES_SCOPES = ["activities:read", "activities:write"]
SCOPES_DICT = {
    "profile": "Privileges over user's own profile",
    "users:read": "Read privileges over users",
    "users:write": "Create privileges over users",
    "gears:read": "Read privileges over gears",
    "gears:write": "Create privileges over gears",
    "activities:read": "Read privileges over activities",
    "activities:write": "Create privileges over activities",
}

# Constants related to user access types
REGULAR_ACCESS = 1
REGULAR_ACCESS_SCOPES = USERS_REGULAR_SCOPES + GEARS_SCOPES + ACTIVITIES_SCOPES
ADMIN_ACCESS = 2
ADMIN_ACCESS_SCOPES = USERS_REGULAR_SCOPES + USERS_ADMIN_SCOPES + GEARS_SCOPES + ACTIVITIES_SCOPES

# Constants related to user active status
USER_ACTIVE = 1
USER_NOT_ACTIVE = 2