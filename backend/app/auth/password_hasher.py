from typing import Tuple
from collections.abc import Iterable
import string
import secrets

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher


class PasswordPolicyError(ValueError):
    """
    Exception raised when a password does not comply with the defined password policy.

    This error should be raised to indicate that a password fails to meet one or more
    requirements such as length, complexity, or character composition.

    Attributes:
        message (str): Explanation of the policy violation.
    """


class PasswordHasher:
    """
    PasswordHasher provides secure password hashing, verification, and password policy enforcement.

    This class encapsulates password hashing logic, verification, and secure password generation
    according to strong password policies. It supports pluggable hashers and ensures that generated
    or validated passwords meet complexity requirements (uppercase, lowercase, digit, punctuation).

    Attributes:
        UPPER (str): All uppercase ASCII letters.
        LOWER (str): All lowercase ASCII letters.
        DIGITS (str): All ASCII digits.
        PUNCTUATION (str): All ASCII punctuation characters.
        ALL (str): Combination of all allowed characters.

    Methods:
        __init__(hasher: Argon2Hasher | BcryptHasher | None = None):
            Initializes the PasswordHasher with an optional custom hasher.

        hash_password(password: str) -> str:
            Hashes a plain text password using the configured password hashing algorithm.

        verify(plain_password: str, hashed_password: str) -> bool:
            Verifies if a plain password matches the given hashed password.

        verify_and_update(plain_password: str, hashed_password: str) -> Tuple[bool, str | None]:
            Verifies a password and updates the hash if the algorithm or parameters have changed.

        generate_password(length: int = 8) -> str:
            Generates a secure random password of specified length, ensuring complexity.

        validate_password(password: str, min_length: int = 8) -> None:
            Validates that a password meets the required security policy, raising PasswordPolicyError if not.

        is_valid_password(password: str, min_length: int = 8) -> bool:
            Checks if a password meets the specified minimum length and password policy requirements.

    Example:
        try:
            PasswordHasher.validate_password("weak")
        except PasswordPolicyError as e:
            print("Oops:", e)
    """

    # Character classes
    UPPER = string.ascii_uppercase
    LOWER = string.ascii_lowercase
    DIGITS = string.digits
    PUNCTUATION = string.punctuation
    ALL = UPPER + LOWER + DIGITS + PUNCTUATION

    def __init__(
        self,
        hasher: (
            Argon2Hasher | BcryptHasher | Iterable[object] | PasswordHash | None
        ) = None,
    ):
        """
        Initialize the password hasher configuration.
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
        """
        Hashes the provided password using the configured password hashing algorithm.

        Args:
            password (str): The plain text password to be hashed.

        Returns:
            str: The resulting hashed password.
        """
        return self._password_hash.hash(password)

    def verify(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verifies whether the provided plain text password matches the given hashed password.

        Args:
            plain_password (str): The plain text password to verify.
            hashed_password (str): The hashed password to compare against.

        Returns:
            bool: True if the plain password matches the hashed password, False otherwise.
        """
        return self._password_hash.verify(plain_password, hashed_password)

    def verify_and_update(
        self, plain_password: str, hashed_password: str
    ) -> Tuple[bool, str | None]:
        """
        Verifies a plain password against a hashed password and updates the hash if necessary.

        Args:
            plain_password (str): The plain text password to verify.
            hashed_password (str): The hashed password to verify against.

        Returns:
            Tuple[bool, str | None]: A tuple where the first element is a boolean indicating
            whether the password is correct, and the second element is the updated hash if
            the hash algorithm has changed or None otherwise.
        """
        return self._password_hash.verify_and_update(plain_password, hashed_password)

    @staticmethod
    def generate_password(length: int = 8) -> str:
        """
        Generate a secure random password of specified length.

        The generated password will contain at least one uppercase letter, one lowercase letter,
        one digit, and one punctuation character to ensure complexity. The remaining characters
        are randomly selected from all allowed character sets.

        Args:
            length (int): The desired length of the password. Must be at least 8.

        Returns:
            str: A randomly generated password meeting the specified criteria.

        Raises:
            ValueError: If the requested length is less than 8.
        """
        if length < 8:
            raise PasswordPolicyError(
                f"Requested length {length!r} is too short; must be ≥ 8."
            )

        # Guarantee at least one from each category
        chars = [
            secrets.choice(PasswordHasher.UPPER),
            secrets.choice(PasswordHasher.LOWER),
            secrets.choice(PasswordHasher.DIGITS),
            secrets.choice(PasswordHasher.PUNCTUATION),
        ]
        for _ in range(length - 4):
            chars.append(secrets.choice(PasswordHasher.ALL))
        secrets.SystemRandom().shuffle(chars)
        return "".join(chars)

    @staticmethod
    def validate_password(
        password: str,
        min_length: int = 8,
        policy_type: str = "strict",
    ) -> None:
        """
        Validates whether the given password meets the required security policy.

        Args:
            password (str): The password string to validate.
            min_length (int, optional): The minimum required length for the password. Defaults to 8.
            policy_type (str, optional): The password policy type to enforce.
                - "strict": Requires uppercase, lowercase, digit, and special character.
                - "length_only": Only enforces minimum length requirement.
                Defaults to "strict".

        Raises:
            PasswordPolicyError: If the password does not meet the policy requirements.
        """
        if len(password) < min_length:
            raise PasswordPolicyError(
                f"Password is too short (got {len(password)}, need ≥ {min_length})."
            )

        # For length_only policy, only min length is enforced
        if policy_type == "length_only":
            return

        # For strict policy, enforce complexity requirements
        if policy_type == "strict":
            if not any(c.isupper() for c in password):
                raise PasswordPolicyError(
                    "Password must contain at least one uppercase letter (A–Z)."
                )

            if not any(c.islower() for c in password):
                raise PasswordPolicyError(
                    "Password must contain at least one lowercase letter (a–z)."
                )

            if not any(c.isdigit() for c in password):
                raise PasswordPolicyError(
                    "Password must contain at least one digit (0–9)."
                )

            if not any(c in PasswordHasher.PUNCTUATION for c in password):
                raise PasswordPolicyError(
                    f"Password must contain at least one special character ({PasswordHasher.PUNCTUATION})."
                )
        else:
            raise PasswordPolicyError(
                f"Unknown password policy type: {policy_type!r}. "
                "Supported types: 'strict', 'length_only'."
            )

    @staticmethod
    def is_valid_password(
        password: str,
        min_length: int = 8,
        policy_type: str = "strict",
    ) -> bool:
        """
        Checks if the provided password meets the specified minimum length and password policy requirements.

        Args:
            password (str): The password string to validate.
            min_length (int, optional): The minimum required length for the password. Defaults to 8.
            policy_type (str, optional): The password policy type to enforce. Defaults to "strict".

        Returns:
            bool: True if the password is valid according to the policy, False otherwise.
        """
        try:
            PasswordHasher.validate_password(password, min_length, policy_type)
            return True
        except PasswordPolicyError:
            return False


def get_password_hasher():
    """
    Returns the password hasher instance.

    This function provides access to the application's password hasher, which is used for securely hashing and verifying passwords.

    Returns:
        password_hasher: An instance of the password hasher used for password operations.
    """
    return password_hasher


# Initialize the PasswordHasher with both Argon2 and Bcrypt support
# Argon2 listed first => new hashes use Argon2; bcrypt remains verifiable for legacy rows.
password_hasher = PasswordHasher(hasher=[Argon2Hasher(), BcryptHasher()])
