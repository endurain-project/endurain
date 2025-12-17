from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field
import core.logger as core_logger


class LoginRequest(BaseModel):
    """
    Schema for login requests containing username and password.

    Attributes:
        username (str): The username of the user. Must be between 1 and 250 characters.
        password (str): The user's password. Must be at least 8 characters long.
    """

    username: str = Field(..., min_length=1, max_length=250)
    password: str = Field(..., min_length=8)


class MFALoginRequest(BaseModel):
    """
    Schema for Multi-Factor Authentication (MFA) login request.

    Attributes:
        username (str): The username of the user attempting to log in. Must be between 1 and 250 characters.
        mfa_code (str): The 6-digit MFA code provided by the user. Must match the pattern: six consecutive digits.
    """

    username: str = Field(..., min_length=1, max_length=250)
    mfa_code: str = Field(..., pattern=r"^\d{6}$")


class MFARequiredResponse(BaseModel):
    """
    Represents a response indicating that Multi-Factor Authentication (MFA) is required.

    Attributes:
        mfa_required (bool): Indicates whether MFA is required. Defaults to True.
        username (str): The username for which MFA is required.
        message (str): A message describing the requirement. Defaults to "MFA verification required".
    """

    mfa_required: bool = True
    username: str
    message: str = "MFA verification required"


class PendingMFALogin:
    """
    A class to manage pending Multi-Factor Authentication (MFA) login sessions.

    This class provides methods to add, retrieve, delete, and check pending login entries
    for users who are in the process of MFA authentication. It uses an internal dictionary
    to store the mapping between usernames and their associated user IDs.

    Also implements progressive lockout mechanism to prevent TOTP brute-force attacks
    (AuthQuake-style vulnerabilities).

    Attributes:
        _store (dict): Internal storage mapping usernames to user IDs for pending logins.
        _failed_attempts (dict): Tracks failed MFA attempts and lockout times per username.

    Methods:
        add_pending_login(username: str, user_id: int):
            Adds a pending login entry for the specified username and user ID.

        get_pending_login(username: str):
            Retrieves the user ID associated with the given username's pending login entry.

        delete_pending_login(username: str):
            Removes the pending login entry for the specified username.

        has_pending_login(username: str):
            Checks if the specified username has a pending login entry.

        is_locked_out(username: str):
            Checks if user is currently locked out from MFA attempts.

        get_lockout_time(username: str):
            Gets the lockout expiry time for a user.

        record_failed_attempt(username: str):
            Records a failed MFA attempt and applies progressive lockout.

        reset_failed_attempts(username: str):
            Resets failed attempt counter on successful verification.

        clear_all():
            Clears all pending login entries from the internal store.
    """

    def __init__(self):
        self._store = {}
        # Failed attempts tracking: {username: (failed_count, lockout_until)}
        self._failed_attempts: dict[str, tuple[int, datetime | None]] = {}

    def add_pending_login(self, username: str, user_id: int):
        """
        Adds a pending login entry for a user.

        Stores the provided username and associated user ID in the internal store,
        marking the user as pending login.

        Args:
            username (str): The username of the user to add.
            user_id (int): The unique identifier of the user.

        """
        self._store[username] = user_id

    def get_pending_login(self, username: str):
        """
        Retrieve the pending login information for a given username.

        Args:
            username (str): The username to look up.

        Returns:
            Any: The pending login information associated with the username, or None if not found.
        """
        return self._store.get(username)

    def delete_pending_login(self, username: str):
        """
        Removes the pending login entry for the specified username from the internal store.

        Args:
            username (str): The username whose pending login entry should be deleted.

        Returns:
            None
        """
        if username in self._store:
            del self._store[username]

    def has_pending_login(self, username: str):
        """
        Checks if the given username has a pending login session.

        Args:
            username (str): The username to check for a pending login.

        Returns:
            bool: True if the username has a pending login session, False otherwise.
        """
        return username in self._store

    def is_locked_out(self, username: str) -> bool:
        """
        Check if user is locked out from MFA attempts.

        Args:
            username: Username to check

        Returns:
            True if user is currently locked out, False otherwise
        """
        if username not in self._failed_attempts:
            return False

        _, lockout_until = self._failed_attempts[username]
        if lockout_until is None:
            return False

        # Check if lockout has expired
        if datetime.now(timezone.utc) > lockout_until:
            # Lockout expired, reset
            del self._failed_attempts[username]
            return False

        return True

    def get_lockout_time(self, username: str) -> datetime | None:
        """
        Get lockout expiry time for user.

        Args:
            username: Username to check

        Returns:
            Lockout expiry datetime if locked out, None otherwise
        """
        if username not in self._failed_attempts:
            return None

        _, lockout_until = self._failed_attempts[username]
        if lockout_until and datetime.now(timezone.utc) <= lockout_until:
            return lockout_until

        return None

    def record_failed_attempt(self, username: str) -> int:
        """
        Record a failed MFA attempt and apply lockout if threshold exceeded.

        Lockout policy:
        - 5 failures: 5 minute lockout
        - 10 failures: 30 minute lockout
        - 15 failures: 2 hour lockout

        Args:
            username: Username that failed MFA verification

        Returns:
            Number of failed attempts
        """
        now = datetime.now(timezone.utc)

        if username in self._failed_attempts:
            failed_count, lockout_until = self._failed_attempts[username]
            # If still locked out, don't increment counter
            if lockout_until and now <= lockout_until:
                return failed_count
            failed_count += 1
        else:
            failed_count = 1

        # Determine lockout duration based on failure count
        lockout_until = None
        if failed_count >= 15:
            lockout_until = now + timedelta(hours=2)
            core_logger.print_to_log(
                f"MFA lockout (2 hours) applied to user {username} after {failed_count} failed attempts",
                "warning",
                context={"username": username, "failed_attempts": failed_count},
            )
        elif failed_count >= 10:
            lockout_until = now + timedelta(minutes=30)
            core_logger.print_to_log(
                f"MFA lockout (30 min) applied to user {username} after {failed_count} failed attempts",
                "warning",
                context={"username": username, "failed_attempts": failed_count},
            )
        elif failed_count >= 5:
            lockout_until = now + timedelta(minutes=5)
            core_logger.print_to_log(
                f"MFA lockout (5 min) applied to user {username} after {failed_count} failed attempts",
                "warning",
                context={"username": username, "failed_attempts": failed_count},
            )

        self._failed_attempts[username] = (failed_count, lockout_until)
        return failed_count

    def reset_failed_attempts(self, username: str) -> None:
        """
        Reset failed attempt counter on successful MFA verification.

        Args:
            username: Username to reset
        """
        if username in self._failed_attempts:
            del self._failed_attempts[username]

    def clear_all(self):
        """
        Removes all items from the internal store, effectively resetting it to an empty state.
        """
        self._store.clear()
        self._failed_attempts.clear()


def get_pending_mfa_store():
    """
    Retrieve the current pending MFA (Multi-Factor Authentication) store.

    Returns:
        dict: The pending MFA store containing MFA-related data.
    """
    return pending_mfa_store


pending_mfa_store = PendingMFALogin()
