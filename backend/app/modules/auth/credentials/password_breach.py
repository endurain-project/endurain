"""Opt-in check of a new password against the Have I Been Pwned range API.

Only the first five hex characters of the password's SHA-1 leave the server (k-anonymity); the API answers every
hash that shares them and the match is made here. The check fails open: a password is never refused because the
service could not be reached.
"""

import hashlib

import httpx2

import core.logger as core_logger
import modules.auth.credentials.password_policy as credentials_password_policy

logger = core_logger.get_logger(__name__)

RANGE_API_URL = "https://api.pwnedpasswords.com/range/"
#: Longest wait for the range API, so a slow service delays a password change by at most this long.
REQUEST_TIMEOUT_SECONDS = 2.0
_PREFIX_LENGTH = 5


def is_breached(password: str) -> bool:
    """Tell whether a password appears in the Have I Been Pwned breach corpus.

    The service is unreachable, slow or erroring: the password is treated as not breached and a warning is logged.
    Neither the password nor any part of its hash is logged.

    Args:
        password: The password as typed; it is hashed in its NFC form.

    Returns:
        True when the range API lists the password's hash with a count above zero.
    """
    digest = (
        hashlib.sha1(credentials_password_policy.hash_form(password).encode("utf-8"), usedforsecurity=False)
        .hexdigest()
        .upper()
    )
    prefix, suffix = digest[:_PREFIX_LENGTH], digest[_PREFIX_LENGTH:]
    try:
        response = httpx2.get(
            f"{RANGE_API_URL}{prefix}",
            headers={"Add-Padding": "true"},
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
        )
        response.raise_for_status()
    except httpx2.HTTPError as err:
        logger.warning(
            "Breached-password check skipped: the range API could not be reached (<error>)",
            extra=core_logger.context(error=type(err).__name__),
        )
        return False
    for line in response.text.splitlines():
        candidate, _, count = line.partition(":")
        # Padding entries carry a count of zero and are not breaches.
        if candidate.strip() == suffix and count.strip().isdigit() and int(count) > 0:
            return True
    return False
