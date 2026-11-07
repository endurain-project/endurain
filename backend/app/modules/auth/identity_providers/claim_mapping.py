"""Translation of identity-provider claims into local user fields."""

from typing import Any

import core.logger as core_logger
import core.types as core_types
import modules.auth.identity_providers.contracts as identity_provider_contracts

logger = core_logger.get_logger(__name__)


_STANDARD_EMAIL_CLAIM = "email"


def _claim_mapping(idp: identity_provider_contracts.IdentityProviderState) -> dict[str, list[str]]:
    """Return the claim names tried for each user field, the provider's custom mapping over the defaults.

    Args:
        idp: The identity provider, whose optional ``user_mapping`` overrides the defaults per field.

    Returns:
        The candidate claim names for each field, in priority order.
    """
    default_mapping = {
        "username": ["preferred_username", "username", "email", "sub"],
        "email": ["email", "mail"],
        "name": ["name", "display_name", "full_name", "displayName"],
    }
    mapping = {**default_mapping, **(idp.user_mapping or {})}
    return {field: [names] if isinstance(names, str) else list(names) for field, names in mapping.items()}


def map_user_claims(idp: identity_provider_contracts.IdentityProviderState, claims: dict[str, Any]) -> dict[str, Any]:
    """Maps user claims from an identity provider to a standardized user dictionary.

    This method takes an identity provider configuration and a dictionary of claims,
    then maps the claims to standard user fields (such as 'username', 'email', and 'name')
    using both default and custom mappings defined in the identity provider.

    Args:
        idp (identity_provider_contracts.IdentityProviderState): The identity provider instance containing optional
            custom user mapping.
        claims (dict[str, Any]): The dictionary of claims received from the identity provider.

    Returns:
        dict[str, Any]: A dictionary mapping standard user fields to their corresponding claim values.
    """
    result = {}
    for field, claim_names in _claim_mapping(idp).items():
        for claim in claim_names:
            if claims.get(claim):
                result[field] = claims[claim]
                break

    if "name" in result:
        # A name with direction controls removed and surrounding whitespace trimmed; one left empty is dropped so
        # the account keeps its username as the display name.
        name = core_types.strip_direction_controls(str(result["name"])).strip()
        if name:
            result["name"] = name
        else:
            del result["name"]

    return result


def is_email_verified(idp: identity_provider_contracts.IdentityProviderState, claims: dict[str, Any]) -> bool:
    """Return ``True`` only when the IdP asserts a verified email and the address came from the ``email`` claim.

    The OIDC ``email_verified`` claim describes the standard ``email`` claim only. An address taken from
    ``mail`` or from a claim the administrator mapped is never treated as verified. Providers may send the
    flag as a JSON boolean (``true``) or, less correctly, as the string ``"true"``; both are accepted. Any
    other value, including a missing claim, is treated as unverified so that email-based account linking
    fails closed.

    Args:
        idp: The identity provider, whose mapping decides which claim supplies the address.
        claims: Raw userinfo/ID-token claims from the identity provider.

    Returns:
        ``True`` if the address came from the ``email`` claim and the provider asserts it as verified.
    """
    source = next((claim for claim in _claim_mapping(idp)["email"] if claims.get(claim)), None)
    if source != _STANDARD_EMAIL_CLAIM:
        return False
    value = claims.get("email_verified")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False
