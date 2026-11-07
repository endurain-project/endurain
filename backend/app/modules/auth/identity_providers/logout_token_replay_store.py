"""Single-use rule for accepted back-channel logout tokens, backed by the platform state.

A logout token stays valid until its ``exp`` plus the clock leeway, so without a record it could be posted again
in that window. Its ``jti`` is claimed once per provider in the shared state store, which holds across every
replica (OIDC Back-Channel Logout 1.0, section 2.6, step 8).
"""

from jasil.providers import StateBackendUnavailableError, StateProvider

import core.exceptions as core_exceptions
import core.hashing as core_hashing

_KEY_PREFIX = "endurain:idp:logout-jti"


def claim_logout_token(state: StateProvider, idp_id: int, jti: str, ttl_seconds: int) -> bool:
    """Record a provider's logout token as used, once.

    The ``jti`` is hashed into the key, so a value the provider chose never becomes part of a state key as is.

    Args:
        state: The platform state provider.
        idp_id: The provider that issued the token.
        jti: The token's ``jti`` claim.
        ttl_seconds: How long the claim must last: until the token can no longer pass the expiry check.

    Returns:
        True when this call used the token, False when it was already used.

    Raises:
        ServiceUnavailableError: When the state store cannot be reached. The token is refused rather than
            accepted without the replay check.
    """
    key = f"{_KEY_PREFIX}:{idp_id}:{core_hashing.sha256_hex(jti)}"
    try:
        return state.set_if_absent(key, b"1", ttl_seconds)
    except StateBackendUnavailableError as err:
        raise core_exceptions.ServiceUnavailableError("Back-channel logout temporarily unavailable") from err
