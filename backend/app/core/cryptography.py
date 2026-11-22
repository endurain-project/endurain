"""Fernet token encryption helpers."""

from typing import overload

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

import core.config as core_config
import core.exceptions as core_exceptions
import core.logger as core_logger

logger = core_logger.get_logger(__name__)


def _configured_fernets() -> list[Fernet]:
    """
    Build one Fernet per configured key, the encrypting key first.

    Returns:
        The Fernets in the order the keys are configured.

    Raises:
        CryptographyError: If the keys cannot be loaded or parsed.
    """
    try:
        raw_keys = core_config.read_secret("FERNET_KEY")
        if raw_keys is None:
            raise ValueError("FERNET_KEY not found in environment or secrets file")
        return [Fernet(key.encode()) for key in core_config.parse_key_list(raw_keys, "FERNET_KEY")]
    except Exception as err:
        logger.debug("Error in _configured_fernets", exc_info=err)

        raise core_exceptions.CryptographyError() from err


def create_fernet_cipher() -> MultiFernet:
    """
    Create a cipher that encrypts with the first configured key and decrypts with any of them.

    Returns:
        MultiFernet initialised with the configured keys.

    Raises:
        CryptographyError: If the keys cannot be loaded or parsed.
    """
    return MultiFernet(_configured_fernets())


def has_older_keys() -> bool:
    """
    Report whether more than one key is configured, so stored values may sit under an older key.

    Returns:
        True when the key list holds an older key besides the encrypting one.

    Raises:
        CryptographyError: If the keys cannot be loaded or parsed.
    """
    return len(_configured_fernets()) > 1


def reencrypt_to_primary_key(token: str) -> str | None:
    """
    Re-encrypt a token under the first configured key when it was encrypted under an older one.

    Args:
        token: Encrypted token string.

    Returns:
        The token encrypted under the first key, or None when it already is.

    Raises:
        UndecryptableError: If no configured key decrypts the token.
        CryptographyError: If the keys cannot be used or re-encryption otherwise fails.
    """
    fernets = _configured_fernets()
    try:
        fernets[0].decrypt(token.encode())
        return None
    except InvalidToken:
        pass
    except Exception as err:
        logger.debug("Error in reencrypt_to_primary_key", exc_info=err)

        raise core_exceptions.CryptographyError() from err

    try:
        return MultiFernet(fernets).rotate(token.encode()).decode()
    except InvalidToken as err:
        logger.debug("Error in reencrypt_to_primary_key", exc_info=err)

        raise core_exceptions.UndecryptableError() from err
    except Exception as err:
        logger.debug("Error in reencrypt_to_primary_key", exc_info=err)

        raise core_exceptions.CryptographyError() from err


@overload
def encrypt_token_fernet(token: str) -> str: ...


@overload
def encrypt_token_fernet(token: None) -> None: ...


@overload
def encrypt_token_fernet(token: object | None) -> str | None: ...


def encrypt_token_fernet(token: object | None) -> str | None:
    """
    Encrypt a token with Fernet symmetric encryption.

    Args:
        token: Token value to encrypt, or None.

    Returns:
        Encrypted token string, or None when input is None.

    Raises:
        CryptographyError: If encryption fails.
    """
    try:
        if token is None:
            return None

        cipher = create_fernet_cipher()

        if not isinstance(token, str):
            token = str(token)

        return cipher.encrypt(token.encode()).decode()
    except core_exceptions.CryptographyError:
        raise
    except Exception as err:
        logger.debug("Error in encrypt_token_fernet", exc_info=err)

        raise core_exceptions.CryptographyError() from err


@overload
def decrypt_token_fernet(encrypted_token: str) -> str: ...


@overload
def decrypt_token_fernet(encrypted_token: None) -> None: ...


@overload
def decrypt_token_fernet(encrypted_token: str | None) -> str | None: ...


def decrypt_token_fernet(encrypted_token: str | None) -> str | None:
    """
    Decrypt a Fernet-encrypted token.

    Args:
        encrypted_token: Encrypted token string, or None.

    Returns:
        Decrypted token string, or None when input is None.

    Raises:
        UndecryptableError: If the token was not encrypted with a configured key, or is corrupt.
        CryptographyError: If the key cannot be used or decryption otherwise fails.
    """
    try:
        if encrypted_token is None:
            return None

        cipher = create_fernet_cipher()

        return cipher.decrypt(encrypted_token.encode()).decode()
    except core_exceptions.CryptographyError:
        raise
    except InvalidToken as err:
        logger.debug("Error in decrypt_token_fernet", exc_info=err)

        raise core_exceptions.UndecryptableError() from err
    except Exception as err:
        logger.debug("Error in decrypt_token_fernet", exc_info=err)

        raise core_exceptions.CryptographyError() from err


def same_secret(first: str | None, second: str | None) -> bool:
    """
    Compare two stored secrets by what they decrypt to.

    Re-encrypting a secret changes its ciphertext but not its value, so a check that a stored secret is
    still the one a caller read must not compare ciphertext.

    Args:
        first: Encrypted secret, or None.
        second: Encrypted secret, or None.

    Returns:
        True when both are None or both decrypt to the same value; False when one is None or either
        cannot be decrypted with a configured key.

    Raises:
        CryptographyError: If the keys cannot be used.
    """
    if first is None or second is None:
        return first is None and second is None
    try:
        return decrypt_token_fernet(first) == decrypt_token_fernet(second)
    except core_exceptions.UndecryptableError:
        return False
