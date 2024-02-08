import os

# Constant related to version
API_VERSION="v0.1.4"

# JWT Token constants
JWT_ALGORITHM = os.environ.get("ALGORITHM")
JWT_EXPIRATION_IN_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES"))
JWT_SECRET_KEY = os.environ.get("SECRET_KEY")

# Constants related to user access types
REGULAR_ACCESS = 1
ADMIN_ACCESS = 2

# Constants related to user active status
USER_ACTIVE = 1
USER_NOT_ACTIVE = 2