"""Token creation and validation logic."""
from datetime import datetime, timedelta, timezone
from typing import Tuple
import secrets
from fastapi import HTTPException, status
from joserfc import jwt
from joserfc.jwk import OctKey

import session.constants as session_constants
import core.logger as core_logger


class TokenManager:
    """Handles JWT token creation and validation."""
    
    def __init__(self, secret_key: str, algorithm: str = "HS256"):
        self.secret_key = secret_key
        self.algorithm = algorithm
        self._key = OctKey.import_key(secret_key)
    
    def create_access_token(self, user_id: int, scopes: list[str]) -> Tuple[str, datetime]:
        """
        Create an access token with expiration.
        
        Args:
            user_id: User ID to encode in token
            scopes: List of permission scopes
            
        Returns:
            Tuple of (token, expiration_datetime)
        """
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=session_constants.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )
        
        payload = {
            "sub": str(user_id),
            "scopes": scopes,
            "exp": expires_at,
            "iat": datetime.now(timezone.utc),
            "token_type": "access"
        }
        
        token = jwt.encode(
            {"alg": self.algorithm},
            payload,
            self._key
        )
        
        return token, expires_at
    
    def create_refresh_token(self, user_id: int) -> Tuple[str, datetime]:
        """
        Create a refresh token with expiration.
        
        Args:
            user_id: User ID to encode in token
            
        Returns:
            Tuple of (token, expiration_datetime)
        """
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=session_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS
        )
        
        payload = {
            "sub": str(user_id),
            "exp": expires_at,
            "iat": datetime.now(timezone.utc),
            "token_type": "refresh"
        }
        
        token = jwt.encode(
            {"alg": self.algorithm},
            payload,
            self._key
        )
        
        return token, expires_at
    
    def decode_token(self, token: str) -> dict:
        """
        Decode and validate a JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded token claims
            
        Raises:
            HTTPException: If token is invalid
        """
        try:
            claims = jwt.decode(token, self._key)
            return claims.claims
        except Exception as err:
            core_logger.print_to_log(
                "Token validation failed",
                "error",
                exc=err,
                context={"token": "[REDACTED]"}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"}
            ) from err
    
    def validate_token_expiration(self, token: str) -> None:
        """
        Validate token expiration and required claims.
        
        Args:
            token: JWT token string
            
        Raises:
            HTTPException: If token is expired or invalid
        """
        try:
            claims_requests = jwt.JWTClaimsRegistry(
                exp={"essential": True},
                sub={"essential": True},
            )
            payload = self.decode_token(token)
            claims_requests.validate(payload)
        except jwt.InvalidClaimError as claims_err:
            core_logger.print_to_log(
                "JWT claims validation error",
                "error",
                exc=claims_err,
                context={"token": "[REDACTED]"}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is missing required claims or is invalid",
                headers={"WWW-Authenticate": "Bearer"}
            ) from claims_err
        except Exception as err:
            core_logger.print_to_log(
                "Error validating token expiration",
                "error",
                exc=err,
                context={"token": "[REDACTED]"}
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is expired or invalid",
                headers={"WWW-Authenticate": "Bearer"}
            ) from err
    
    @staticmethod
    def create_csrf_token() -> str:
        """
        Generate a CSRF token.
        
        Returns:
            URL-safe CSRF token string
        """
        return secrets.token_urlsafe(32)
