import os

# Constant related to version
API_VERSION = "v0.2.1"

# JWT Token constants
JWT_ALGORITHM = os.environ.get("ALGORITHM")
JWT_EXPIRATION_IN_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES"))
JWT_SECRET_KEY = os.environ.get("SECRET_KEY")

# Scopes definition
USERS_ADMIN_SCOPES = ["users:read", "users:edit", "users:write"]
USERS_REGULAR_SCOPES = ["users:read", "users:edit"]
GEARS_SCOPES = ["gears:read", "gears:edit", "gears:write"]
ACTIVITIES_SCOPES = ["activities:read", "activities:edit", "activities:write"]
SCOPES_DICT = {
    "users:read": "Read privileges over users",
    "users:write": "Create privileges over users",
    "users:edit": "Edit privileges over users",
    "gears:read": "Read privileges over gears",
    "gears:write": "Create privileges over gears",
    "gears:edit": "Edit privileges over gears",
    "activities:read": "Read privileges over activities",
    "activities:write": "Create privileges over activities",
    "activities:edit": "Edit privileges over activities",
}

# Constants related to user access types
REGULAR_ACCESS = 1
REGULAR_ACCESS_SCOPES = USERS_REGULAR_SCOPES + GEARS_SCOPES + ACTIVITIES_SCOPES
ADMIN_ACCESS = 2
ADMIN_ACCESS_SCOPES = USERS_ADMIN_SCOPES + GEARS_SCOPES + ACTIVITIES_SCOPES

# Constants related to user active status
USER_ACTIVE = 1
USER_NOT_ACTIVE = 2
