"""NIST SP 800-63B-4 password policy: length, blocklist and account details, with Unicode normalisation.

Composition rules are deliberately absent. Passwords are compared and stored in Unicode NFC form so that the same
text typed on two platforms is the same password.
"""

import functools
import gzip
import unicodedata
from pathlib import Path

import modules.auth.credentials.contracts as credentials_contracts

_BLOCKLIST_PATH = Path(__file__).parent / "data" / "password_blocklist.txt.gz"
_APPLICATION_NAME = "endurain"


def hash_form(password: str) -> str:
    """Return the form a password is hashed in: Unicode NFC.

    Args:
        password: The password as typed.

    Returns:
        The NFC-normalised password.
    """
    return unicodedata.normalize("NFC", password)


def compare_form(value: str) -> str:
    """Return the form a value is compared in against the blocklist and account details: NFC, lowercase.

    Args:
        value: A password or an account detail.

    Returns:
        The NFC-normalised, lowercased value.
    """
    return hash_form(value).lower()


@functools.cache
def load_blocklist() -> frozenset[str]:
    """Load the bundled list of common passwords once per process.

    The file is immutable data shipped with the application, so the loaded set is not shared request state.

    Returns:
        The blocklist entries, already in compare form.
    """
    with gzip.open(_BLOCKLIST_PATH, "rt", encoding="utf-8") as handle:
        return frozenset(line.rstrip("\n") for line in handle if line.strip())


def check_password(password: str, min_length: int, username: str, email: str) -> None:
    """Refuse a password that is too short, too common or equal to an account detail.

    Args:
        password: The password as typed.
        min_length: Minimum length in Unicode code points of the NFC form.
        username: The account's username.
        email: The account's email address.

    Raises:
        PasswordTooShortError: If the NFC form is shorter than ``min_length``.
        PasswordTooCommonError: If the password is on the blocklist.
        PasswordMatchesAccountError: If the whole password equals the username, the email, the email's local
            part or the application name.
    """
    if len(hash_form(password)) < min_length:
        raise credentials_contracts.PasswordTooShortError(f"The password must be at least {min_length} characters long")
    candidate = compare_form(password)
    if candidate in load_blocklist():
        raise credentials_contracts.PasswordTooCommonError()
    account_details = {compare_form(username), compare_form(email), compare_form(email.partition("@")[0])}
    account_details.add(_APPLICATION_NAME)
    if candidate in account_details:
        raise credentials_contracts.PasswordMatchesAccountError()
