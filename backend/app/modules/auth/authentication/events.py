"""Domain event channels owned by the authentication package.

Events may be persisted, so a payload carries ids only: never an API key, a username or a password.
"""

from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

# Published when a request authenticated with an API key, so its last-used time can be recorded off the request path.
API_KEY_USED = "auth.api_key_used"
# Published when 100 failed password sign-ins in a row lock an account, so its owner is told.
ACCOUNT_LOCKED = "auth.account_locked"
# Published when 100 wrong MFA codes in a row lock an account's MFA sign-in, so its owner is told.
MFA_LOCKED = "auth.mfa_locked"


class ApiKeyUsedPayload(VersionedPayload):
    """Validated payload for the ``auth.api_key_used`` event.

    Attributes:
        api_key_id: The key that authenticated a request.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    api_key_id: str


class AccountLockedPayload(VersionedPayload):
    """Validated payload for the ``auth.account_locked`` event.

    Attributes:
        user_id: The user whose account was locked.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: int


class MfaLockedPayload(VersionedPayload):
    """Validated payload for the ``auth.mfa_locked`` event.

    Attributes:
        user_id: The user whose MFA sign-in was locked.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: int
