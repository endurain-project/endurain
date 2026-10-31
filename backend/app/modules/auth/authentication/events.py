"""Domain event channels owned by the authentication package.

Events may be persisted, so the payload carries the API key id only: never the key itself.
"""

from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

# Published when a request authenticated with an API key, so its last-used time can be recorded off the request path.
API_KEY_USED = "auth.api_key_used"


class ApiKeyUsedPayload(VersionedPayload):
    """Validated payload for the ``auth.api_key_used`` event.

    Attributes:
        api_key_id: The key that authenticated a request.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    api_key_id: str
