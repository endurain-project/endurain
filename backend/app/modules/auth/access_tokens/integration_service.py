"""Operations exposed by the access-token package to auth peers."""

import core.key_derivation as core_key_derivation
import modules.auth.access_tokens.contracts as access_tokens_contracts
import modules.auth.access_tokens.service as access_tokens_service
import modules.auth.computation as auth_computation

TokenManager = access_tokens_service.TokenManager
TokenType = access_tokens_contracts.TokenType


def get_token_manager() -> access_tokens_service.TokenManager:
    """Return the configured token manager."""
    return access_tokens_service.get_token_manager()


def _keyed_hmac(value: str, purpose: str) -> str:
    secret_key = core_key_derivation.derive_key(purpose)
    if secret_key is None:
        raise ValueError("SECRET_KEY is not configured")
    return auth_computation.hmac_sha256(value, secret_key)


def hmac_sha256(value: str) -> str:
    """Hash a value with the key derived for token digests."""
    return _keyed_hmac(value, core_key_derivation.TOKEN_HMAC)


def hmac_sha256_under_every_key(value: str) -> tuple[str, ...]:
    """Hash a value with the token-digest key of every ``SECRET_KEY`` entry.

    A digest stored before a rotation was made with a key that is no longer first, so a lookup or a comparison
    needs the digest under each listed key. The first element is what :func:`hmac_sha256` returns, which is what
    a new digest is stored as.

    Args:
        value: The value to hash.

    Returns:
        One digest per key, in ``SECRET_KEY`` order.

    Raises:
        ValueError: If ``SECRET_KEY`` is not configured.
    """
    keys = core_key_derivation.derive_keys(core_key_derivation.TOKEN_HMAC)
    if not keys:
        raise ValueError("SECRET_KEY is not configured")
    return tuple(auth_computation.hmac_sha256(value, key) for key in keys)


def derive_email_token(value: str) -> str:
    """Derive a raw emailed token from a value with the key derived for emailed tokens.

    The key is not the one that digests tokens for storage, so a stored digest is never a token that
    can be mailed.
    """
    return _keyed_hmac(value, core_key_derivation.EMAIL_TOKEN)


def scopes_for_access_type(access_type: str) -> tuple[str, ...]:
    """Return the scopes a user of an access type holds."""
    return access_tokens_service.scopes_for_access_type(access_type)
