import secrets
import uuid

from enum import Enum

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from joserfc import jwt
from joserfc.errors import (
    InvalidPayloadError,
    MissingClaimError,
    ExpiredTokenError,
    InvalidTokenError,
    InsecureClaimError,
    InvalidClaimError,
)
from joserfc.jwk import OctKey

import auth.constants as auth_constants

import users.users.schema as users_schema

import core.logger as core_logger
import core.config as core_config


class TokenType(Enum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenManager:
    """
    TokenManager is a utility class for managing JSON Web Tokens (JWT) in user sessions.

    This class provides methods for creating, decoding, validating, and extracting claims from JWTs,
    as well as generating secure CSRF tokens. It supports configurable encryption algorithms and
    integrates with application logging and exception handling for robust security and error reporting.

    Attributes:
        algorithm (str): The algorithm used for token operations (default: "HS256").
        _key: The imported key object used for cryptographic operations.

    Methods:
        __init__(secret_key: str, algorithm: str = "HS256"):

        get_token_claim(token: str, claim: str) -> str | list[str] | int:

        decode_token(token: str) -> dict:

        validate_token_expiration(token: str) -> None:

        create_token(session_id: str, user: users_schema.UsersRead, token_type: TokenType) -> tuple[datetime, str]:

        create_csrf_token() -> str:
            Generates a secure random CSRF (Cross-Site Request Forgery) token.

        HTTPException: Raised for invalid, expired, or missing claims in JWT tokens.
        ValueError: Raised for missing or invalid parameters during token creation.
    """

    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        """
        Initializes the TokenManager with the provided secret key and algorithm.

        Args:
            secret_key (str): The secret key used for token encryption and decryption.
            algorithm (str, optional): The algorithm to use for token operations. Defaults to "HS256".

        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self._key = OctKey.import_key(secret_key)

    def get_token_claim(self, token: str, claim: str) -> str | list[str] | int:
        """
        Retrieves a specific claim from a decoded JWT token.

        Args:
            token (str): The JWT token string to decode.
            claim (str): The name of the claim to retrieve from the token.

        Returns:
            str | list[str] | int: The value of the requested claim, which can be a string, list of strings, or integer.

        Raises:
            HTTPException: If the claim is not found in the token or if there is an error retrieving the claim.
        """
        try:
            # Decode the token
            payload = self.decode_token(token)

            # Get the claim from the payload and return it
            return payload.claims[claim]
        except KeyError as err:
            core_logger.print_to_log(
                f"Claim '{claim}' not found in token: {err}",
                "error",
                exc=err,
                context={"token": "[REDACTED]"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Claim '{claim}' is missing in the token.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from err
        except Exception as err:
            core_logger.print_to_log(
                f"Error retrieving claim '{claim}' from token: {err}",
                "error",
                exc=err,
                context={"token": "[REDACTED]"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Unable to retrieve claim '{claim}' from token.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from err

    def decode_token(self, token: str) -> dict:
        """
        Decodes a JWT token and returns its payload as a dictionary.

        Args:
            token (str): The JWT token to decode.

        Returns:
            dict: The decoded payload from the token.

        Raises:
            HTTPException: If the token cannot be decoded, raises an HTTP 401 Unauthorized exception.
        """
        try:
            # Decode the token and return the payload
            return jwt.decode(token, OctKey.import_key(self.secret_key))
        except InvalidPayloadError as payload_err:
            core_logger.print_to_log(
                f"Invalid token payload: {payload_err}",
                "error",
                exc=payload_err,
                context={"token": "[REDACTED]"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            ) from payload_err
        except Exception as err:
            core_logger.print_to_log(
                f"Error decoding token: {err}",
                "error",
                exc=err,
                context={"token": "[REDACTED]"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to decode token",
                headers={"WWW-Authenticate": "Bearer"},
            ) from err

    def validate_token_expiration(self, token: str) -> None:
        """
        Validates the expiration and required claims of a JWT token.

        This method checks if the provided JWT token contains all essential claims,
        verifies its expiration, and ensures it is not used before its valid time.
        If any required claim is missing, the token is expired, not yet valid, or contains
        insecure/invalid claims, appropriate HTTP exceptions are raised and errors are logged.

        Args:
            token (str): The JWT token to validate.

        Raises:
            HTTPException: If the token is missing required claims, expired, not yet valid,
                           or contains invalid claims.
        """
        try:
            # Define required claims
            claims_requests = jwt.JWTClaimsRegistry(
                sid={"essential": True},
                iss={"essential": True, "value": f"{core_config.ENDURAIN_HOST}"},
                aud={"essential": True, "value": f"{core_config.ENDURAIN_HOST}"},
                sub={"essential": True},
                scope={"essential": True},
                iat={"essential": True},
                nbf={"essential": True},
                exp={"essential": True},
                jti={"essential": True},
            )

            # Decode the token to get the payload
            payload = self.decode_token(token)

            # Validate token expiration
            claims_requests.validate(payload.claims)
        except MissingClaimError as missing_err:
            core_logger.print_to_log(
                f"JWT missing claim error: {missing_err}",
                "error",
                exc=missing_err,
                context={"token": "[REDACTED]"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is missing required claims.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from missing_err
        except ExpiredTokenError as expired_err:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is expired.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from expired_err
        except InvalidTokenError as invalid_err:
            core_logger.print_to_log(
                f"JWT is not valid yet error: {invalid_err}",
                "error",
                exc=invalid_err,
                context={"token": "[REDACTED]"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is not valid yet.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from invalid_err
        except InsecureClaimError as insecure_err:
            core_logger.print_to_log(
                f"JWT insecure claim error: {insecure_err}",
                "error",
                exc=insecure_err,
                context={"token": "[REDACTED]"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has insecure claims.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from insecure_err
        except InvalidClaimError as claims_err:
            core_logger.print_to_log(
                f"JWT claims validation error: {claims_err}",
                "error",
                exc=claims_err,
                context={"token": "[REDACTED]"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has invalid claims.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from claims_err
        except Exception as err:
            core_logger.print_to_log(
                f"Error validating token expiration: {err}",
                "error",
                exc=err,
                context={"token": "[REDACTED]"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is expired or invalid.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from err

    def create_token(
        self,
        session_id: str,
        user: users_schema.UsersRead,
        token_type: TokenType,
    ) -> tuple[datetime, str]:
        """
        Creates a JWT token for a user session with appropriate access scope and expiration.

        Args:
            session_id (str): The unique identifier for the session.
            user (users_schema.UsersRead): The user object containing user details.
            token_type (TokenType): The type of token to create (access or refresh).

        Returns:
            tuple[datetime, str]: A tuple containing the token's expiration datetime and the encoded JWT token string.

        Raises:
            ValueError: If required parameters are missing or invalid.
        """
        # Check user access level and set scope accordingly
        if user.access_type == users_schema.UserAccessType.REGULAR:
            scope = auth_constants.REGULAR_ACCESS_SCOPE
        else:
            scope = auth_constants.ADMIN_ACCESS_SCOPE

        exp = datetime.now(timezone.utc) + timedelta(
            minutes=auth_constants.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )
        if token_type == TokenType.REFRESH:
            exp = datetime.now(timezone.utc) + timedelta(
                days=auth_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS
            )

        # Set now
        now = int(datetime.now(timezone.utc).timestamp())

        scope_dict = {
            "sid": session_id,
            "iss": core_config.ENDURAIN_HOST,
            "aud": core_config.ENDURAIN_HOST,
            "sub": user.id,
            "scope": scope,
            "iat": now,
            "nbf": now,
            "exp": exp,
            "jti": str(uuid.uuid4()),
        }

        encoded_token = jwt.encode(
            {"alg": self.algorithm},
            scope_dict.copy(),
            OctKey.import_key(self.secret_key),
        )

        # Return the expiration and the encoded token
        return exp, encoded_token

    @staticmethod
    def create_csrf_token() -> str:
        """
        Generate a secure random CSRF (Cross-Site Request Forgery) token.

        Returns:
            str: A URL-safe, securely generated random string suitable for use as a CSRF token.
        """
        return secrets.token_urlsafe(32)


def get_token_manager() -> TokenManager:
    """
    Returns the singleton instance of TokenManager.

    This function provides access to the global token_manager instance,
    which is responsible for managing authentication tokens within the application.

    Returns:
        TokenManager: The singleton token manager instance.
    """
    return token_manager


# Validate required configuration before creating token manager
if auth_constants.JWT_SECRET_KEY is None:
    raise ValueError("JWT_SECRET_KEY must be set in environment variables")

if auth_constants.JWT_ALGORITHM is None:
    raise ValueError("JWT_ALGORITHM must be set in environment variables")

token_manager = TokenManager(
    auth_constants.JWT_SECRET_KEY, auth_constants.JWT_ALGORITHM
)
