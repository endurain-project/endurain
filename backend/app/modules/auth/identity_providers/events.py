"""Domain event channels owned by the identity-providers module.

Payloads carry ids only: events are persisted, so no token may be put in one.
"""

from typing import ClassVar

from jasil.event_versioning import VersionedPayload
from pydantic import ConfigDict

# Published after a session refresh found a linked identity-provider token about to expire.
IDP_TOKEN_REFRESH_REQUESTED = "auth.idp_token_refresh_requested"  # noqa: S105 - event channel name, not a credential

# Published after an identity provider was linked to a user's account.
IDP_LINKED = "auth.idp_linked"


class IdpTokenRefreshPayload(VersionedPayload):
    """Validated payload for the ``auth.idp_token_refresh_requested`` event.

    Attributes:
        user_id: The user whose identity-provider tokens are to be refreshed.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: int


class IdpLinkedPayload(VersionedPayload):
    """Validated payload for the ``auth.idp_linked`` event.

    Attributes:
        user_id: The user whose account gained the link.
        idp_id: The identity provider that was linked.
    """

    model_config = ConfigDict(extra="ignore")

    SCHEMA_VERSION: ClassVar[int] = 1

    user_id: int
    idp_id: int
