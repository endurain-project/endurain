"""Translation of identity-provider claims into local user fields."""

from typing import Any

import core.logger as core_logger
import modules.auth.identity_providers.contracts as identity_provider_contracts

logger = core_logger.get_logger(__name__)


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
    # Default mapping
    default_mapping = {
        "username": ["preferred_username", "username", "email", "sub"],
        "email": ["email", "mail"],
        "name": ["name", "display_name", "full_name", "displayName"],
    }

    # Merge with custom mapping
    mapping = {**default_mapping, **(idp.user_mapping or {})}

    result = {}
    for field, claim_names in mapping.items():
        if isinstance(claim_names, str):
            claim_names = [claim_names]
        for claim in claim_names:
            if claims.get(claim):
                result[field] = claims[claim]
                break

    return result


def is_email_verified(claims: dict[str, Any]) -> bool:
    """Return ``True`` only when the IdP asserts a verified email.

    Honors the standard OIDC ``email_verified`` claim. Providers may
    send it as a JSON boolean (``true``) or, less correctly, as the
    string ``"true"``; both are accepted. Any other value — including
    a missing claim — is treated as *unverified* so that email-based
    account linking fails closed.

    Args:
        claims: Raw userinfo/ID-token claims from the identity provider.

    Returns:
        ``True`` if the email is explicitly asserted as verified.
    """
    value = claims.get("email_verified")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False
