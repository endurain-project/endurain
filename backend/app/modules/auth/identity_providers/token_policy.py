"""Policy deciding when a stored identity-provider token is refreshed, kept or cleared."""

from datetime import UTC, datetime, timedelta
from enum import Enum

import core.logger as core_logger
import modules.auth.identity_provider_links.contracts as auth_identity_links_contracts

logger = core_logger.get_logger(__name__)

# Constants for token rotation policy
MAX_IDP_TOKEN_AGE_DAYS = 90
TOKEN_EXPIRY_THRESHOLD_MINUTES = 5
TOKEN_REFRESH_RATE_LIMIT_MINUTES = 1


class TokenAction(Enum):
    """Actions to take for an IdP token based on policy evaluation.

    Attributes:
        SKIP: Token is valid, no action needed
        REFRESH: Token is close to expiry, should be refreshed
        CLEAR: Token is too old or invalid, should be cleared
    """

    SKIP = "skip"
    REFRESH = "refresh"
    CLEAR = "clear"


def is_token_expired_by_age(link: auth_identity_links_contracts.IdentityLinkRead) -> bool:
    """Check if an IdP refresh token has exceeded the maximum age policy.

    According to security best practices, refresh tokens should have a maximum lifetime
    to limit the window of exposure. This method checks if a token is older than the
    configured maximum age.

    Args:
        link (auth_identity_links_contracts.IdentityLinkRead): The user-IdP link containing token metadata.

    Returns:
        bool: True if the token exceeds maximum age, False otherwise.

    Policy:
        - Tokens older than MAX_IDP_TOKEN_AGE_DAYS are considered expired
        - Age is calculated from idp_refresh_token_updated_at (last refresh time)
        - If idp_refresh_token_updated_at is None, use linked_at (initial link time)

    Security Note:
        Enforcing maximum token age:
        - Reduces window of exposure for compromised tokens
        - Forces periodic re-authentication (validates user access)
        - Limits damage from undetected token theft
        - Complies with security frameworks (e.g., NIST 800-63B)
    """
    if not link or not link.idp_refresh_token:
        # No token stored - not expired
        return False

    now = datetime.now(UTC)

    # Determine when the token was first issued or last refreshed
    token_timestamp = link.idp_refresh_token_updated_at or link.linked_at

    if not token_timestamp:
        # No timestamp available - cannot determine age (should not happen)
        logger.warning(
            "Warning: IdP link user_id=<user_id>, idp_id=<idp_id> has no timestamp for age calculation",
            extra=core_logger.context(user_id=link.user_id, idp_id=link.idp_id),
        )
        return False

    # Calculate token age (TIMESTAMPTZ returns aware datetimes)
    token_age = now - token_timestamp

    # Check if token exceeds maximum age
    max_age = timedelta(days=MAX_IDP_TOKEN_AGE_DAYS)
    return token_age > max_age


def should_refresh_idp_token(link: auth_identity_links_contracts.IdentityLinkRead) -> TokenAction:
    """Determine what action to take for an IdP token based on expiry and age policies.

    This method checks multiple conditions to decide the appropriate action:
    1. Token age - if token exceeds maximum age, it must be cleared
    2. Token existence - whether a refresh token is stored
    3. Token expiry - whether the access token is close to expiry
    4. Rate limiting - whether the token was refreshed very recently

    Args:
        link (auth_identity_links_contracts.IdentityLinkRead): The user-IdP link containing token metadata.

    Returns:
        TokenAction: The action to take (SKIP, REFRESH, or CLEAR).

    Policy:
        - CLEAR if refresh token exceeds maximum age
        - SKIP if no refresh token is stored
        - SKIP if expiry time is unknown (assume token is valid)
        - SKIP if token was refreshed in last defined time(rate limiting)
        - REFRESH if access token expires within defined minutes
        - SKIP if token is still valid and not close to expiry

    Example usage:
        link = identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id(
            user_id, idp_id, db
        )
        action = should_refresh_idp_token(link)
        if action == TokenAction.REFRESH:
            tokens.refresh_idp_session(user_id, idp_id, claims)
        elif action == TokenAction.CLEAR:
            identity_provider_links_integration.clear_user_identity_provider_refresh_token(
                user_id, idp_id, db
            )
    """
    # Check if refresh token exists
    if not link or not link.idp_refresh_token:
        return TokenAction.SKIP

    # Check if token has exceeded maximum age (security policy)
    if is_token_expired_by_age(link):
        logger.info(
            "IdP refresh token for user_id=<user_id>, idp_id=<idp_id> has exceeded maximum age "
            "(<MAX_IDP_TOKEN_AGE_DAYS> days). Will be cleared.",
            extra=core_logger.context(
                user_id=link.user_id, idp_id=link.idp_id, MAX_IDP_TOKEN_AGE_DAYS=MAX_IDP_TOKEN_AGE_DAYS
            ),
        )
        return TokenAction.CLEAR

    # Check if we know when the access token expires
    if not link.idp_access_token_expires_at:
        # No expiry info - assume token is still valid
        return TokenAction.SKIP

    now = datetime.now(UTC)

    # Check if token was refreshed very recently (rate limiting)
    if link.idp_refresh_token_updated_at:
        time_since_refresh = now - link.idp_refresh_token_updated_at
        if time_since_refresh < timedelta(minutes=TOKEN_REFRESH_RATE_LIMIT_MINUTES):
            # Refreshed less than defined - don't refresh again
            return TokenAction.SKIP

    # Check if access token is close to expiry
    time_until_expiry = link.idp_access_token_expires_at - now
    if time_until_expiry < timedelta(minutes=TOKEN_EXPIRY_THRESHOLD_MINUTES):
        # Token expires soon - should refresh
        return TokenAction.REFRESH

    # Token is still valid and not close to expiry
    return TokenAction.SKIP
