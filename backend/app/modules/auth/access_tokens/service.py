"""JWT token issuance and validation for the authentication module.

Defines :class:`TokenType`, :class:`TokenManager` (issue/decode/validate JWTs
and mint CSRF tokens) and a singleton accessor used as a FastAPI dependency.
"""

import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Final

from joserfc import jwt
from joserfc.errors import (
    DecodeError,
    ExpiredTokenError,
    InsecureClaimError,
    InvalidClaimError,
    InvalidPayloadError,
    InvalidTokenError,
    MissingClaimError,
)
from joserfc.jwk import OctKey
from joserfc.jwt import Token

import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger
import modules.auth.access_tokens.contracts as access_tokens_contracts
import modules.auth.constants as auth_constants
import modules.users.users.schema as users_schema

logger = core_logger.get_logger(__name__)

TokenType = access_tokens_contracts.TokenType


JWT_ALLOWED_ALGORITHMS: Final[frozenset[str]] = frozenset({"HS256"})
JWT_ALGORITHM: Final[str] = os.environ.get("ALGORITHM", "HS256")
if JWT_ALGORITHM not in JWT_ALLOWED_ALGORITHMS:
    raise ValueError(f"ALGORITHM={JWT_ALGORITHM!r} is not in the allow-list {sorted(JWT_ALLOWED_ALGORITHMS)}.")
JWT_SECRET_KEY: Final[str | None] = core_config.read_secret("SECRET_KEY")

if not JWT_SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is required")


class TokenManager:
    """TokenManager is a utility class for managing JSON Web Tokens (JWT) in user.

    sessions.

    This class provides methods for creating, decoding, validating, and
    extracting claims from JWTs, as well as generating secure CSRF tokens. It
    supports configurable encryption algorithms and integrates with application
    logging and exception handling for robust security and error reporting.

    Attributes:
        algorithm (str): The algorithm used for token operations (default: "HS256").
            _key: The imported key object used for cryptographic operations.

    Methods:
        __init__(secret_key: str, algorithm: str = "HS256"):
        get_token_claim(token: str, claim: str) -> str | list[str] | int:
        decode_token(token: str) -> dict:
        validate_token_expiration(token: str, expected_type: TokenType) -> None:
        create_token(session_id: str, user: users_schema.UsersRead, token_type: TokenType, ttl: timedelta) -> tuple[datetime, str]:
        create_csrf_token() -> str:
            Generates a secure random CSRF (Cross-Site Request Forgery) token.
        UnauthenticatedError: Raised for invalid, expired, or missing claims in JWT tokens.
        ValueError: Raised for missing or invalid parameters during token creation.
    """

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        """Initializes the TokenManager with the provided secret key and algorithm.

        Args:
            secret_key (str): The secret key used for token encryption and
                decryption.
            algorithm (str, optional): The algorithm to use for token
                operations. Defaults to "HS256". Must be a member of
                :data:`modules.auth.constants.JWT_ALLOWED_ALGORITHMS` so that the
                allow-list passed to ``jwt.decode`` cannot drift from the
                signing algorithm.

        """
        if algorithm not in JWT_ALLOWED_ALGORITHMS:
            raise ValueError(f"algorithm={algorithm!r} is not in the JWT allow-list {sorted(JWT_ALLOWED_ALGORITHMS)}.")
        self.secret_key = secret_key
        self.algorithm = algorithm
        self._key = OctKey.import_key(secret_key)

    def get_token_claim(self, token: str, claim: str) -> str | list[str] | int:
        """Retrieves a specific claim from a decoded JWT token.

        Args:
            token (str): The JWT token string to decode.
            claim (str): The name of the claim to retrieve from the token.

        Returns:
            str | list[str] | int: The value of the requested claim, which can
                be a string, list of strings, or integer.

        Raises:
            UnauthenticatedError: If the claim is not found in the token or if there
                is an error retrieving the claim.
        """
        try:
            # Decode the token
            payload = self.decode_token(token)

            # Get the claim from the payload and return it
            return payload.claims[claim]
        except KeyError as err:
            logger.warning(
                "Requested token claim is missing",
                extra=core_logger.context(credential="token", claim=claim),
            )
            raise core_exceptions.UnauthenticatedError(f"Claim '{claim}' is missing in the token.") from err
        except core_exceptions.UnauthenticatedError:
            # decode_token already raised a properly-formed 401; re-raise as-is.
            raise
        except Exception as err:
            logger.error(
                "Unexpected error retrieving token claim",
                exc_info=err,
                extra=core_logger.context(credential="token"),
            )
            raise core_exceptions.UnauthenticatedError("Unable to retrieve claim") from err

    def decode_token(self, token: str) -> Token:
        """Decodes a JWT token and returns the parsed Token object.

        Args:
            token (str): The JWT token to decode.

        Returns:
            joserfc.jwt.Token: The decoded token (use ``.claims`` to access
                payload claims).

        Raises:
            UnauthenticatedError: If the token cannot be decoded, raises an HTTP 401
                Unauthorized exception.
        """
        try:
            # Decode the token and return the payload. The ``algorithms``
            # allow-list is mandatory: without it, joserfc would accept any
            # algorithm the token header advertises (including ``none`` or
            # asymmetric variants), which would let an attacker who controls
            # the unauthenticated token bypass the HMAC signature check.
            return jwt.decode(token, self._key, algorithms=[self.algorithm])
        except InvalidPayloadError as payload_err:
            logger.warning(
                "Invalid token payload",
                extra=core_logger.context(credential="token"),
            )
            raise core_exceptions.UnauthenticatedError("Invalid token payload") from payload_err
        except DecodeError as decode_err:
            logger.warning(
                "Error decoding token",
                extra=core_logger.context(credential="token"),
            )
            raise core_exceptions.UnauthenticatedError("Unable to decode token") from decode_err
        except Exception as err:
            logger.error(
                "Unexpected error decoding token",
                exc_info=err,
                extra=core_logger.context(credential="token"),
            )
            raise core_exceptions.UnauthenticatedError("Unable to decode token") from err

    def validate_token_expiration(
        self,
        token: str,
        expected_type: TokenType,
    ) -> None:
        """Validates expiration, required claims, and type of a JWT.

        Checks that the token contains all essential claims, is not expired or
        used before its valid time, and that the ``typ`` claim matches the
        expected token type. This prevents refresh tokens from being used as
        access tokens and vice versa.

        Args:
            token: The JWT token to validate.
            expected_type: The expected token type
                (``TokenType.ACCESS`` or
                ``TokenType.REFRESH``).

        Raises:
            UnauthenticatedError: If the token is missing required claims, expired,
                not yet valid, contains invalid claims, or has the wrong type.
        """
        try:
            # Define required claims
            claims_requests = jwt.JWTClaimsRegistry(
                sid={"essential": True},
                iss={
                    "essential": True,
                    "value": f"{core_config.settings.ENDURAIN_HOST}",
                },
                aud={
                    "essential": True,
                    "value": f"{core_config.settings.ENDURAIN_HOST}",
                },
                sub={"essential": True},
                scope={"essential": True},
                iat={"essential": True},
                nbf={"essential": True},
                exp={"essential": True},
                jti={"essential": True},
                typ={
                    "essential": True,
                    "value": expected_type.value,
                },
            )

            # Decode the token to get the payload
            payload = self.decode_token(token)

            # Validate token claims (incl. expiration and typ)
            claims_requests.validate(payload.claims)
        except MissingClaimError as missing_err:
            logger.warning(
                "JWT is missing required claims",
                extra=core_logger.context(credential="token"),
            )
            raise core_exceptions.UnauthenticatedError("Token is missing required claims.") from missing_err
        except ExpiredTokenError as expired_err:
            raise core_exceptions.UnauthenticatedError("Token is expired.") from expired_err
        except InvalidTokenError as invalid_err:
            logger.warning(
                "JWT is not valid yet",
                extra=core_logger.context(credential="token"),
            )
            raise core_exceptions.UnauthenticatedError("Token is not valid yet.") from invalid_err
        except InsecureClaimError as insecure_err:
            logger.warning(
                "JWT contains an insecure claim",
                extra=core_logger.context(credential="token"),
            )
            raise core_exceptions.UnauthenticatedError("Token has insecure claims.") from insecure_err
        except InvalidClaimError as claims_err:
            logger.warning(
                "JWT claim validation failed",
                extra=core_logger.context(credential="token"),
            )
            raise core_exceptions.UnauthenticatedError("Token has invalid claims.") from claims_err
        except core_exceptions.UnauthenticatedError:
            # decode_token already raised a properly-formed 401; re-raise as-is.
            raise
        except Exception as err:
            logger.error(
                "Unexpected error validating token",
                exc_info=err,
                extra=core_logger.context(credential="token"),
            )
            raise core_exceptions.UnauthenticatedError("Token expired or invalid.") from err

    def validate_access_expiration_logged(self, access_token: str) -> None:
        """Validate an access token's expiration and log failures consistently.

        Wraps :meth:`validate_token_expiration` for ``TokenType.ACCESS`` and
        applies the shared logging policy used by the access-token validation
        dependency and principal resolution: a refused token is an expected 401, so
        it logs at ``debug`` here (the manager already warned about anything but an
        expiry). The original :class:`core_exceptions.UnauthenticatedError` is re-raised
        unchanged so callers keep the same 401 semantics.

        Args:
            access_token: The raw JWT access token to validate.

        Raises:
            UnauthenticatedError: 401 if the token is missing claims, expired, not
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
        session_id: str,
        user: users_schema.UsersRead,
        token_type: TokenType,
        ttl: timedelta,
    ) -> tuple[datetime, str]:
        """Creates a JWT token for a user session with appropriate access scope.

        and expiration.

        Args:
            session_id (str): The unique identifier for the session.
            user (users_schema.UsersRead): The user object containing user
                details.
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
            "sid": session_id,
            "iss": core_config.settings.ENDURAIN_HOST,
            "aud": core_config.settings.ENDURAIN_HOST,
            "sub": str(user.id),
            "scope": scope,
            "iat": now,
            "nbf": now,
            "exp": exp,
            "jti": str(uuid.uuid4()),
            "typ": token_type.value,
        }

        encoded_token = jwt.encode(
            {"alg": self.algorithm},
            scope_dict.copy(),
            self._key,
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
        The regular scopes for a regular user, the administrator scopes otherwise.
    """
    if access_type == users_schema.UserAccessType.REGULAR.value:
        return auth_constants.REGULAR_ACCESS_SCOPE
    return auth_constants.ADMIN_ACCESS_SCOPE


def get_token_manager() -> TokenManager:
    """Returns the singleton instance of TokenManager.

    This function provides access to the global token_manager instance,
    which is responsible for managing authentication tokens within the
    application.

    Returns:
        TokenManager: The singleton token manager instance.
    """
    return token_manager


# Validate required configuration before creating token manager
if JWT_SECRET_KEY is None:
    raise ValueError("JWT_SECRET_KEY must be set in environment variables")

if JWT_ALGORITHM is None:
    raise ValueError("JWT_ALGORITHM must be set in environment variables")

token_manager = TokenManager(JWT_SECRET_KEY, JWT_ALGORITHM)
