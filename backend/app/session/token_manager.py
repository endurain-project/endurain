import secrets
import uuid

from enum import Enum

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from joserfc import jwt
from joserfc.jwk import OctKey

import session.constants as session_constants

import users.user.schema as users_schema

import core.logger as core_logger
import core.config as core_config


class TokenType(Enum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenManager:
    """
    TokenManager is a utility class for managing JSON Web Tokens (JWT) in authentication workflows.
    This class provides methods to create, decode, and validate JWT tokens, as well as extract specific claims such as user ID and scope. It also supports CSRF token generation.
    Attributes:
        algorithm (str): The algorithm used for token operations (default: "HS256").
        _key: The imported key object used for JWT operations.
    Methods:
        __init__(secret_key: str, algorithm: str = "HS256"):
        get_token_user_id(token: str) -> int:
        get_token_scopes(token: str) -> list[str]:
        decode_token(token: str) -> dict:
        validate_token_expiration(token: str) -> None:
        create_token(data: dict) -> str:
        create_csrf_token() -> str:
            Generates a secure random CSRF (Cross-Site Request Forgery) token.
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

    def get_token_user_id(self, token: str) -> int:
        """
        Extracts and returns the user ID from a given JWT token.

        Decodes the provided token and retrieves the 'sub' claim, which represents the user ID.
        If the 'sub' claim is missing or any error occurs during extraction, logs the error and raises an HTTP 401 Unauthorized exception.

        Args:
            token (str): The JWT token from which to extract the user ID.

        Returns:
            int: The user ID extracted from the token.

        Raises:
            HTTPException: If the 'sub' claim is missing or if any error occurs during token decoding.
        """
        try:
            # Decode the token
            payload = self.decode_token(token)

            # Get the user id from the payload and return it
            return payload.claims["sub"]
        except KeyError as err:
            core_logger.print_to_log(
                f"User ID claim not found in token: {err}",
                "error",
                exc=err,
                context={"token": "[REDACTED]"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User ID claim is missing in the token.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from err
        except Exception as err:
            core_logger.print_to_log(
                f"Error retrieving user ID from token: {err}",
                "error",
                exc=err,
                context={"token": "[REDACTED]"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to retrieve user ID from token.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from err

    def get_token_scopes(self, token: str) -> list[str]:
        """
        Extracts the list of scope from a given JWT token.

        Args:
            token (str): The JWT token from which to extract scope.

        Returns:
            list[str]: A list of scope present in the token.

        Raises:
            HTTPException: If the "scope" claim is missing from the token payload or if any error occurs during extraction.
        """
        try:
            # Decode the token
            payload = self.decode_token(token)

            # Get the scope from the payload and return it
            return payload.claims["scope"]
        except KeyError as err:
            core_logger.print_to_log(
                f"scope claim not found in token: {err}",
                "error",
                exc=err,
                context={"token": "[REDACTED]"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="scope claim is missing in the token.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from err
        except Exception as err:
            core_logger.print_to_log(
                f"Error retrieving scope from token: {err}",
                "error",
                exc=err,
                context={"token": "[REDACTED]"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to retrieve scope from token.",
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

        This method checks if the provided JWT token contains the essential claims
        ('exp' and 'sub') and verifies that the token has not expired. If the token
        is missing required claims or is invalid, an HTTP 401 Unauthorized exception
        is raised. Any errors encountered during validation are logged.

        Args:
            token (str): The JWT token to validate.

        Raises:
            HTTPException: If the token is missing required claims, is expired, or is invalid.
        """
        try:
            # Define required claims
            claims_requests = jwt.JWTClaimsRegistry(
                exp={"essential": True},
                sub={"essential": True},
            )

            # Decode the token to get the payload
            payload = self.decode_token(token)

            # Validate token expiration
            claims_requests.validate(payload.claims)
        except jwt.InvalidClaimError as claims_err:
            core_logger.print_to_log(
                f"JWT claims validation error: {claims_err}",
                "error",
                exc=claims_err,
                context={"token": "[REDACTED]"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is missing required claims or is invalid.",
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
        user: users_schema.UserRead,
        token_type: TokenType,
        data: dict | None = None,
    ) -> str:
        scope_dict = data if data else {}

        if data is None:
            # Check user access level and set scope accordingly
            if user.access_type == users_schema.UserAccessType.REGULAR:
                scope = session_constants.REGULAR_ACCESS_SCOPE
            else:
                scope = session_constants.ADMIN_ACCESS_SCOPE

            exp = datetime.now(timezone.utc) + timedelta(
                minutes=session_constants.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
            )
            if token_type == TokenType.REFRESH:
                exp = datetime.now(timezone.utc) + timedelta(
                    days=session_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS
                )

            # Set now
            now = int(datetime.now(timezone.utc).timestamp())

            scope_dict = {
                "iss": core_config.ENDURAIN_HOST,
                "aud": core_config.ENDURAIN_HOST,
                "sub": user.id,
                "scope": scope,
                "iat": now,
                "nbf": now,
                "exp": exp,
                "jti": str(uuid.uuid4()),
            }

        # Encode the data and return the token
        return jwt.encode(
            {"alg": self.algorithm},
            scope_dict.copy(),
            OctKey.import_key(self.secret_key),
        )

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


token_manager = TokenManager(
    session_constants.JWT_SECRET_KEY, session_constants.JWT_ALGORITHM
)
