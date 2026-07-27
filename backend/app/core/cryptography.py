"""Fernet token encryption helpers."""

from cryptography.fernet import Fernet
from fastapi import HTTPException, status

import core.config as core_config
import core.logger as core_logger

logger = core_logger.get_logger(__name__)


def create_fernet_cipher() -> Fernet:
    """
    Create a Fernet cipher from the configured key.

    Returns:
        Fernet cipher initialised with the configured key.

    Raises:
        HTTPException: If the key cannot be loaded or parsed.
    """
    try:
        key = core_config.read_secret("FERNET_KEY")
        if key is None:
            raise ValueError("FERNET_KEY not found in environment or secrets file")
        return Fernet(key.encode())
    except Exception as err:
        logger.error(f"Error in create_fernet_cipher: {type(err).__name__}", exc_info=err)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def encrypt_token_fernet(token: object | None) -> str | None:
    """
    Encrypt a token with Fernet symmetric encryption.

    Args:
        token: Token value to encrypt, or None.

    Returns:
        Encrypted token string, or None when input is None.

    Raises:
        HTTPException: If encryption fails.
    """
    try:
        if token is None:
            return None

        cipher = create_fernet_cipher()

        if not isinstance(token, str):
            token = str(token)

        return cipher.encrypt(token.encode()).decode()
    except Exception as err:
        logger.error(f"Error in encrypt_token_fernet: {type(err).__name__}", exc_info=err)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def decrypt_token_fernet(encrypted_token: str | None) -> str | None:
    """
    Decrypt a Fernet-encrypted token.

    Args:
        encrypted_token: Encrypted token string, or None.

    Returns:
        Decrypted token string, or None when input is None.

    Raises:
        HTTPException: If decryption fails.
    """
    try:
        if encrypted_token is None:
            return None

        cipher = create_fernet_cipher()

        return cipher.decrypt(encrypted_token.encode()).decode()
    except Exception as err:
        logger.error(f"Error in decrypt_token_fernet: {type(err).__name__}", exc_info=err)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
