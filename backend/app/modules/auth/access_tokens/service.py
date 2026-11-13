"""JWT token issuance and validation for the authentication module.

Defines :class:`TokenType`, :class:`TokenManager` (issue/decode/validate JWTs
and mint CSRF tokens) and a singleton accessor used as a FastAPI dependency.
"""

import secrets
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Final

from joserfc import jwt
from joserfc.errors import (
    ExpiredTokenError,
    InsecureClaimError,
    InvalidClaimError,
    InvalidPayloadError,
    JoseError,
    MissingClaimError,
)
from joserfc.jwt import Token

import core.config as core_config
import core.exceptions as core_exceptions
import core.jwt_keys as core_jwt_keys
import core.logger as core_logger
import modules.auth.access_tokens.contracts as access_tokens_contracts
import modules.auth.constants as auth_constants
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)

TokenType = access_tokens_contracts.TokenType


JWT_ALLOWED_ALGORITHMS: Final[frozenset[str]] = core_jwt_keys.ALLOWED_ALGORITHMS
JWT_ALGORITHM: Final[str] = core_jwt_keys.ALGORITHM

if not core_jwt_keys.SIGNING_KEYS or not core_jwt_keys.REFRESH_SIGNING_KEYS:
    raise ValueError("SECRET_KEY environment variable is required")

#: The path of the endpoint that redeems a refresh token; with the server's host it is a refresh token's audience.
REFRESH_ENDPOINT_PATH: Final[str] = core_config.ROOT_PATH + "/auth/refresh"

#: The claims whose invalid value means a time still in the future, beyond the clock leeway.
_TIME_CLAIMS_NOT_YET_VALID: Final[frozenset[str]] = frozenset({"nbf", "iat"})


def token_audience(token_type: TokenType) -> str:
    """Return the ``aud`` claim a token of a kind carries, and must carry to verify as that kind.

    An access token is for the API as a resource server, named by the server's host (RFC 9068 section 3). A refresh
    token is for the endpoint that redeems it, named by that endpoint's URL, so neither kind is accepted where the
    other is expected (RFC 8725 section 3.9). Logging out, which ends the refresh token's session, accepts it too.

    Args:
        token_type: The kind of token.

    Returns:
        The audience URL.
    """
    host = core_config.settings.ENDURAIN_HOST
    return host if token_type is TokenType.ACCESS else host + REFRESH_ENDPOINT_PATH


class TokenManager:
    """Issues and validates Endurain's access and refresh tokens, and mints CSRF tokens.

    Each kind of token is signed with keys of its own and carries its own ``typ`` header and ``aud`` claim, so one
    kind never verifies as the other. Each kind has a list of keys: the first signs, every one verifies, and a token
    is verified with the key its ``kid`` header names, so a key can rotate without ending the tokens it signed.

    Attributes:
        algorithm: The one signing algorithm tokens are issued and accepted with.
    """

    def __init__(self, access_keys: Sequence[str], refresh_keys: Sequence[str], algorithm: str = "HS256"):
        """Initializes the TokenManager with the keys of each kind of token and the algorithm.

        Args:
            access_keys: The access-token keys; the first signs, every one verifies.
            refresh_keys: The refresh-token keys; the first signs, every one verifies.
            algorithm: The algorithm to use for token operations. Must be a member of
                :data:`JWT_ALLOWED_ALGORITHMS` so that the allow-list passed to ``jwt.decode`` cannot drift from the
                signing algorithm.

        Raises:
            ValueError: If the algorithm is not allowed or a kind of token has no key.
        """
        if algorithm not in JWT_ALLOWED_ALGORITHMS:
            raise ValueError(f"algorithm={algorithm!r} is not in the JWT allow-list {sorted(JWT_ALLOWED_ALGORITHMS)}.")
        if not access_keys or not refresh_keys:
            raise ValueError("A token manager needs at least one access-token key and one refresh-token key.")
        self.algorithm = algorithm
        self._signing_keys = {
            TokenType.ACCESS: core_jwt_keys.import_key(access_keys[0]),
            TokenType.REFRESH: core_jwt_keys.import_key(refresh_keys[0]),
        }
        self._verification_keys = {
            TokenType.ACCESS: core_jwt_keys.key_set(access_keys),
            TokenType.REFRESH: core_jwt_keys.key_set(refresh_keys),
        }

    def get_token_claim(self, token: str, claim: str, token_type: TokenType) -> str | list[str] | int:
        """Retrieves a specific claim from a decoded JWT token.

        Args:
            token (str): The JWT token string to decode.
            claim (str): The name of the claim to retrieve from the token.
            token_type: The kind of token, which decides the keys its signature is checked with.

        Returns:
            str | list[str] | int: The value of the requested claim, which can
                be a string, list of strings, or integer.

        Raises:
            InvalidTokenError: If the claim is not found in the token or if there
                is an error retrieving the claim.
        """
        try:
            # Decode the token
            payload = self.decode_token(token, token_type)

            # Get the claim from the payload and return it
            return payload.claims[claim]
        except KeyError as err:
            logger.warning(
                "Requested token claim is missing",
                extra=core_logger.context(credential="token", claim=claim),
            )
            raise core_exceptions.InvalidTokenError(f"Claim '{claim}' is missing in the token.") from err
        except core_exceptions.UnauthenticatedError:
            # decode_token already raised a properly-formed 401; re-raise as-is.
            raise
        except Exception as err:
            logger.error(
                "Unexpected error retrieving token claim",
                exc_info=err,
                extra=core_logger.context(credential="token"),
            )
            raise core_exceptions.InvalidTokenError("Unable to retrieve claim") from err

    def decode_token(self, token: str, token_type: TokenType) -> Token:
        """Decodes a JWT token and returns the parsed Token object.

        Args:
            token (str): The JWT token to decode.
            token_type: The kind of token; its signature is checked only with the keys of that kind.

        Returns:
            joserfc.jwt.Token: The decoded token (use ``.claims`` to access
                payload claims).

        Raises:
            InvalidTokenError: If the token cannot be decoded, raises an HTTP 401
                Unauthorized exception.
        """
        try:
            # The shared decoder pins the one allowed algorithm; see ``core.jwt_keys.decode``.
            return core_jwt_keys.decode(token, self._verification_keys[token_type], self.algorithm)
        except InvalidPayloadError as payload_err:
            logger.warning(
                "Invalid token payload",
                extra=core_logger.context(credential="token"),
            )
            raise core_exceptions.InvalidTokenError("Invalid token payload") from payload_err
        except JoseError as decode_err:
            # A malformed, forged or unsupported token (bad signature, algorithm or header) is client input.
            logger.warning(
                "Error decoding token",
                extra=core_logger.context(credential="token"),
            )
            raise core_exceptions.InvalidTokenError("Unable to decode token") from decode_err
        except Exception as err:
            logger.error(
                "Unexpected error decoding token",
                exc_info=err,
                extra=core_logger.context(credential="token"),
            )
            raise core_exceptions.InvalidTokenError("Unable to decode token") from err

    def validate_token_expiration(
        self,
        token: str,
        expected_type: TokenType,
    ) -> None:
        """Validates expiration, required claims, and type of a JWT.

        Checks that the token is signed with a key of the expected kind, contains all essential claims, names the
        audience of that kind and a known client, is not expired or used before its valid time, and that the ``typ``
        header matches the expected token type. This prevents refresh tokens from being used as access tokens and
        vice versa. Times are judged with :data:`core.jwt_keys.CLOCK_LEEWAY_SECONDS` of leeway, so a replica whose
        clock is slightly ahead or behind the one that issued the token still accepts it.

        Args:
            token: The JWT token to validate.
            expected_type: The expected token type
                (``TokenType.ACCESS`` or
                ``TokenType.REFRESH``).

        Raises:
            InvalidTokenError: If the token is missing required claims, expired,
                not yet valid, contains invalid claims, or has the wrong type.
        """
        try:
            # Define required claims
            claims_requests = jwt.JWTClaimsRegistry(
                leeway=core_jwt_keys.CLOCK_LEEWAY_SECONDS,
                sid={"essential": True},
                iss={
                    "essential": True,
                    "value": core_config.settings.ENDURAIN_HOST,
                },
                aud={
                    "essential": True,
                    "value": token_audience(expected_type),
                },
                sub={"essential": True},
                scope={"essential": True},
                client_id={
                    "essential": True,
                    "values": [client_type.value for client_type in auth_constants.ClientType],
                },
                iat={"essential": True},
                nbf={"essential": True},
                exp={"essential": True},
                jti={"essential": True},
            )

            # Decode the token to get the payload
            payload = self.decode_token(token, expected_type)

            # The JOSE ``typ`` header names the kind of token (RFC 8725 section 3.11).
            if payload.header.get("typ") != expected_type.header_type:
                logger.warning(
                    "JWT has the wrong type for this use",
                    extra=core_logger.context(credential="token"),
                )
                raise core_exceptions.InvalidTokenError("Token has the wrong type.")

            # Validate token claims (incl. expiration)
            claims_requests.validate(payload.claims)
        except MissingClaimError as missing_err:
            logger.warning(
                "JWT is missing required claims",
                extra=core_logger.context(credential="token"),
            )
            raise core_exceptions.InvalidTokenError("Token is missing required claims.") from missing_err
        except ExpiredTokenError as expired_err:
            raise core_exceptions.InvalidTokenError("Token is expired.") from expired_err
        except InsecureClaimError as insecure_err:
            logger.warning(
                "JWT contains an insecure claim",
                extra=core_logger.context(credential="token"),
            )
            raise core_exceptions.InvalidTokenError("Token has insecure claims.") from insecure_err
        except InvalidClaimError as claims_err:
            # joserfc raises the same error for a time in the future and for a wrong value; the claim tells them apart.
            if claims_err.claim in _TIME_CLAIMS_NOT_YET_VALID:
                logger.warning(
                    "JWT is not valid yet",
                    extra=core_logger.context(credential="token"),
                )
                raise core_exceptions.InvalidTokenError("Token is not valid yet.") from claims_err
            logger.warning(
                "JWT claim <claim> failed validation",
                extra=core_logger.context(credential="token", claim=claims_err.claim),
            )
            raise core_exceptions.InvalidTokenError("Token has invalid claims.") from claims_err
        except core_exceptions.UnauthenticatedError:
            # decode_token already raised a properly-formed 401; re-raise as-is.
            raise
        except Exception as err:
            logger.error(
                "Unexpected error validating token",
                exc_info=err,
                extra=core_logger.context(credential="token"),
            )
            raise core_exceptions.InvalidTokenError("Token expired or invalid.") from err

    def validate_access_expiration_logged(self, access_token: str) -> None:
        """Validate an access token's expiration and log failures consistently.

        Wraps :meth:`validate_token_expiration` for ``TokenType.ACCESS`` and
        applies the shared logging policy used by the access-token validation
        dependency and principal resolution: a refused token is an expected 401, so
        it logs at ``debug`` here (the manager already warned about anything but an
        expiry). The original :class:`core_exceptions.InvalidTokenError` is re-raised
        unchanged so callers keep the same 401 semantics.

        Args:
            access_token: The raw JWT access token to validate.

        Raises:
            InvalidTokenError: 401 if the token is missing claims, expired, not
                yet valid, or otherwise invalid.
        """
        try:
            self.validate_token_expiration(access_token, TokenType.ACCESS)
        except core_exceptions.UnauthenticatedError:
            logger.debug(
                "Access token validation failed",
                extra=core_logger.context(credential="access_token"),
            )
            raise

    def create_token(
        self,
        session_id: uuid.UUID,
        user: users_schema.UserRead,
        client_type: auth_constants.ClientType,
        token_type: TokenType,
        ttl: timedelta,
    ) -> tuple[datetime, str]:
        """Creates a JWT token for a user session with appropriate access scope and expiration.

        The token is signed with the key of its kind and names its kind's audience. Its ``client_id`` claim is the
        client type of the session (RFC 9068 section 2.2), and ``nbf`` equals ``iat``: a replica whose clock is
        behind the issuer's still accepts it within the clock leeway.

        Args:
            session_id (uuid.UUID): The unique identifier for the session.
            user (users_schema.UserRead): The user object containing user
                details.
            client_type: The client type the session was created for.
            token_type (TokenType): The type of token to create (access or
                refresh).
            ttl (timedelta): How long the token lives, from the session policy.

        Returns:
            tuple[datetime, str]: A tuple containing the token's expiration
                datetime and the encoded JWT token string.

        Raises:
            ValueError: If required parameters are missing or invalid.
        """
        scope = scopes_for_access_type(user.access_type)

        exp = datetime.now(UTC) + ttl

        # Set now
        now = int(datetime.now(UTC).timestamp())

        scope_dict = {
            "sid": str(session_id),
            "iss": core_config.settings.ENDURAIN_HOST,
            "aud": token_audience(token_type),
            "sub": str(user.id),
            "client_id": client_type.value,
            "scope": " ".join(scope),
            "iat": now,
            "nbf": now,
            "exp": exp,
            "jti": str(uuid.uuid4()),
        }

        signing_key = self._signing_keys[token_type]
        encoded_token = jwt.encode(
            {"alg": self.algorithm, "typ": token_type.header_type, "kid": signing_key.kid},
            scope_dict.copy(),
            signing_key,
        )

        # Return the expiration and the encoded token
        return exp, encoded_token

    @staticmethod
    def create_csrf_token() -> str:
        """Generate a secure random CSRF (Cross-Site Request Forgery) token.

        Returns:
            str: A URL-safe, securely generated random string suitable for use
                as a CSRF token.
        """
        return secrets.token_urlsafe(32)


def scopes_for_access_type(access_type: str) -> tuple[str, ...]:
    """Return the scopes a user of an access type holds.

    Args:
        access_type: The user's access type.

    Returns:
        The regular scopes for a regular user, the administrator scopes for an administrator.

    Raises:
        ProcessingError: If the access type is neither, so no scope is granted on a value the code does not know.
    """
    match access_type:
        case users_schema.UserAccessType.REGULAR:
            return auth_constants.REGULAR_ACCESS_SCOPE
        case users_schema.UserAccessType.ADMIN:
            return auth_constants.ADMIN_ACCESS_SCOPE
    logger.error("Refusing to derive scopes for an unknown access type")
    raise core_exceptions.ProcessingError


def get_token_manager() -> TokenManager:
    """Returns the singleton instance of TokenManager.

    This function provides access to the global token_manager instance,
    which is responsible for managing authentication tokens within the
    application.

    Returns:
        TokenManager: The singleton token manager instance.
    """
    return token_manager


token_manager = TokenManager(core_jwt_keys.SIGNING_KEYS, core_jwt_keys.REFRESH_SIGNING_KEYS, JWT_ALGORITHM)
