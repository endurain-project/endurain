from pydantic import BaseModel, Field


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

    Attributes:
        _store (dict): Internal storage mapping usernames to user IDs for pending logins.

    Methods:
        add_pending_login(username: str, user_id: int):
            Adds a pending login entry for the specified username and user ID.

        get_pending_login(username: str):
            Retrieves the user ID associated with the given username's pending login entry.

        delete_pending_login(username: str):
            Removes the pending login entry for the specified username.

        has_pending_login(username: str):
            Checks if the specified username has a pending login entry.

        clear_all():
            Clears all pending login entries from the internal store.
    """

    def __init__(self):
        self._store = {}

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

    def clear_all(self):
        """
        Removes all items from the internal store, effectively resetting it to an empty state.
        """
        self._store.clear()


def get_pending_mfa_store():
    """
    Retrieve the current pending MFA (Multi-Factor Authentication) store.

    Returns:
        dict: The pending MFA store containing MFA-related data.
    """
    return pending_mfa_store


pending_mfa_store = PendingMFALogin()
