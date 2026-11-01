"""Password hashing and verification.

Defines :class:`PasswordHasher` (Argon2-first with bcrypt fallback for legacy
hashes) and the singleton accessor used as a FastAPI dependency.
"""

import secrets
from collections.abc import Iterable

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher


class PasswordHasher:
    """Hashes and verifies secrets with an Argon2-first, bcrypt-fallback scheme.

    It hashes whatever it is given: password policy and Unicode normalisation live in
    :mod:`modules.auth.credentials.password_policy`, so the same hasher also serves refresh tokens and backup codes.

    Methods:
        hash_password(password: str) -> str:
            Hashes a plain text secret with the configured algorithm.

        verify_password(plain_password: str, hashed_password: str) -> bool:
            Verifies if a plain secret matches the given hash.

        verify_and_update(plain_password: str, hashed_password: str) -> tuple[bool, str | None]:
            Verifies a secret and returns a new hash if the algorithm or parameters have changed.

        dummy_verify() -> None:
            Spends the time of a real verify so a missing account is indistinguishable from a wrong password.
    """

    def __init__(
        self,
        hasher: (Argon2Hasher | BcryptHasher | Iterable[object] | PasswordHash | None) = None,
    ):
        """Initialize the password hasher configuration.

        Args:
            hasher (Argon2Hasher | BcryptHasher | Iterable[object] | PasswordHash | None, optional):
                The hasher(s) to use for password hashing. Can be:
                - None: Uses the strongest recommended configuration.
                - PasswordHash: Uses the provided PasswordHash instance.
                - Argon2Hasher or BcryptHasher: Uses the single hasher instance.
                - Iterable: Uses a list of hasher instances.

        Raises:
            TypeError: If the provided hasher is not of a supported type.
        """
        if hasher is None:
            # Default: strongest recommended config
            self._password_hash = PasswordHash.recommended()
        elif isinstance(hasher, PasswordHash):
            # Already a PasswordHash instance
            self._password_hash = hasher
        elif isinstance(hasher, (Argon2Hasher, BcryptHasher)):
            # Single hasher instance
            self._password_hash = PasswordHash([hasher])
        elif isinstance(hasher, Iterable):
            # Iterable of hashers
            self._password_hash = PasswordHash(list(hasher))
        else:
            raise TypeError(
                f"Unsupported hasher type: {type(hasher).__name__}. Must be Argon2Hasher, BcryptHasher, Iterable, PasswordHash, or None."
            )

    def hash_password(self, password: str) -> str:
        """Hashes the provided password using the configured password hashing algorithm.

        Args:
            password (str): The plain text password to be hashed.

        Returns:
            str: The resulting hashed password.
        """
        return self._password_hash.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verifies whether the provided plain text password matches the given hashed password.

        Args:
            plain_password (str): The plain text password to verify.
            hashed_password (str): The hashed password to compare against.

        Returns:
            bool: True if the plain password matches the hashed password, False otherwise.
        """
        return self._password_hash.verify(plain_password, hashed_password)

    def verify_and_update(self, plain_password: str, hashed_password: str) -> tuple[bool, str | None]:
        """Verifies a plain password against a hashed password and updates the hash if necessary.

        Args:
            plain_password (str): The plain text password to verify.
            hashed_password (str): The hashed password to verify against.

        Returns:
            tuple[bool, str | None]: A tuple where the first element is a boolean indicating
            whether the password is correct, and the second element is the updated hash if
            the hash algorithm has changed or None otherwise.
        """
        return self._password_hash.verify_and_update(plain_password, hashed_password)

    def dummy_verify(self) -> None:
        """Run a constant-time-equivalent password verify against a dummy hash.

        Used by the login and MFA-verify endpoints on the "username/user
        not found" branch to equalise wall-clock latency with the
        "found, wrong password" branch. Without this, an unauthenticated
        attacker can enumerate valid usernames by measuring response
        time, because Argon2 is deliberately tuned to hundreds of
        milliseconds and a fast bail-out on the not-found branch is
        trivially distinguishable from a real verify.

        The dummy hash is generated lazily once per process from a
        random throwaway password so that no real user's hash is reused
        and the verify always returns ``False``.
        """
        # Lazily generate a dummy hash so cost is paid only on first
        # call (typically during the first failed login attempt). We
        # use a random throwaway password and discard it; what we keep
        # is its hash, which we then verify a *different* random
        # password against — the verify is guaranteed to return False
        # but performs the full Argon2 work.
        if not hasattr(self, "_dummy_hash"):
            throwaway = secrets.token_urlsafe(32)
            self._dummy_hash = self._password_hash.hash(throwaway)
        # Verify a *different* random string so the result is always
        # False; we ignore the return value — the call exists purely
        # for its timing side effect.
        self._password_hash.verify(secrets.token_urlsafe(32), self._dummy_hash)


def get_password_hasher():
    """Returns the password hasher instance.

    This function provides access to the application's password hasher, which is used for securely hashing and verifying passwords.

    Returns:
        password_hasher: An instance of the password hasher used for password operations.
    """
    return password_hasher


# Initialize the PasswordHasher with both Argon2 and Bcrypt support
# Argon2 listed first => new hashes use Argon2; bcrypt remains verifiable for legacy rows.
password_hasher = PasswordHasher(hasher=[Argon2Hasher(), BcryptHasher()])
