import os
from cryptography.fernet import Fernet
from fastapi import HTTPException, status

import core.logger as core_logger
import core.config as core_config


def create_fernet_cipher():
    """
    Creates and returns a Fernet cipher object using a key from the environment variable 'FERNET_KEY'.

    Returns:
        Fernet: An instance of the Fernet cipher initialized with the provided key.

    Raises:
        HTTPException: If there is an error retrieving the key or creating the Fernet cipher, 
                       raises an HTTPException with a 500 Internal Server Error status code.
    """
    try:
        # Get the key from environment variable or file and encode it to bytes
        key = core_config.read_secret("FERNET_KEY")
        if key is None:
            raise ValueError("FERNET_KEY not found in environment or secrets file")
        return Fernet(key.encode())
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in create_fernet_cipher: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def encrypt_token_fernet(token) -> str | None:
    """
    Encrypts a given token using Fernet symmetric encryption.

    Args:
        token (Any): The token to be encrypted. If not a string, it will be converted to a string.
                     If None, the function returns None.

    Returns:
        str | None: The encrypted token as a string, or None if the input token is None.

    Raises:
        HTTPException: If an error occurs during encryption, raises an HTTPException with
                       status code 500 (Internal Server Error) and logs the exception.
    """
    try:
        if token is None:
            # If the token is None, return None
            return None

        # Create a Fernet cipher
        cipher = create_fernet_cipher()

        # Convert to string if token is not already a string
        if not isinstance(token, str):
            token = str(token)

        # Encrypt the token
        return cipher.encrypt(token.encode()).decode()
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in encrypt_token_fernet: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err


def decrypt_token_fernet(encrypted_token) -> str | None:
    """
    Decrypts an encrypted token using Fernet symmetric encryption.

    Args:
        encrypted_token (str | None): The encrypted token as a string. If None, the function returns None.

    Returns:
        str | None: The decrypted token as a string if decryption is successful, or None if the input is None.

    Raises:
        HTTPException: If an error occurs during decryption, raises an HTTPException with a 500 Internal Server Error status code and logs the exception.
    """
    try:
        if encrypted_token is None:
            # If the encrypted token is None, return None
            return None

        # Create a Fernet cipher
        cipher = create_fernet_cipher()

        # Decrypt the token
        return cipher.decrypt(encrypted_token.encode()).decode()
    except Exception as err:
        # Log the exception
        core_logger.print_to_log(
            f"Error in decrypt_token_fernet: {err}", "error", exc=err
        )

        # Raise an HTTPException with a 500 Internal Server Error status code
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error",
        ) from err
