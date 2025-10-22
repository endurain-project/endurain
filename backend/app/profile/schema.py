from pydantic import BaseModel


class MFARequest(BaseModel):
    """
    Request model for Multi-Factor Authentication (MFA) verification.

    Attributes:
        mfa_code (str): The MFA verification code provided by the user for authentication.
    """

    mfa_code: str


class MFASetupRequest(BaseModel):
    """
    Request model for Multi-Factor Authentication (MFA) setup.

    Attributes:
        mfa_code (str): The MFA verification code provided by the user during setup.
    """

    mfa_code: str


class MFASetupResponse(BaseModel):
    """
    Response model for MFA (Multi-Factor Authentication) setup.

    Attributes:
        secret (str): The secret key used for generating TOTP codes.
        qr_code (str): The QR code image data (base64 or URL) for scanning with an authenticator app.
        app_name (str): The application name displayed in the authenticator app. Defaults to "Endurain".
    """

    secret: str
    qr_code: str
    app_name: str = "Endurain"


class MFADisableRequest(BaseModel):
    """
    Request model for disabling Multi-Factor Authentication (MFA).

    Attributes:
        mfa_code (str): The MFA verification code required to disable MFA for the user's account.
    """

    mfa_code: str


class MFAStatusResponse(BaseModel):
    """
    Response model for MFA (Multi-Factor Authentication) status.

    Attributes:
        mfa_enabled (bool): Indicates whether MFA is enabled for the user.
    """

    mfa_enabled: bool


class MFASecretStore:

    def __init__(self):
        """
        Initialize a new instance of the class.

        Creates an empty dictionary to store data.

        Args:
            None

        Returns:
            None
        """
        self._store = {}

    def add_secret(self, user_id: int, secret: str):
        """
        Add or update a secret for a specific user.

        Args:
            user_id (int): The unique identifier of the user.
            secret (str): The secret value to store for the user.

        Returns:
            None
        """
        self._store[user_id] = secret

    def get_secret(self, user_id: int):
        """
        Retrieve the secret associated with a specific user.

        Args:
            user_id (int): The unique identifier of the user whose secret is to be retrieved.

        Returns:
            The secret value associated with the user_id, or None if not found.
            The return type depends on the implementation of the store.

        Raises:
            May raise exceptions depending on the underlying store implementation.
        """
        return self._store.get(user_id)

    def delete_secret(self, user_id: int):
        """
        Delete a secret associated with a specific user.

        This method removes the secret entry for the given user_id from the internal store.
        If the user_id exists in the store, it will be deleted; otherwise, no action is taken.

        Args:
            user_id (int): The unique identifier of the user whose secret should be deleted.

        Returns:
            None

        Example:
            >>> secrets = SecretsManager()
            >>> secrets.delete_secret(123)
        """
        if user_id in self._store:
            del self._store[user_id]

    def has_secret(self, user_id: int):
        """
        Check if a user has a stored secret.

        Args:
            user_id (int): The unique identifier of the user.

        Returns:
            bool: True if the user has a secret stored, False otherwise.
        """
        return user_id in self._store

    def clear_all(self):
        """
        Clear all items from the store.

        This method removes all key-value pairs from the internal store,
        leaving it empty.

        Returns:
            None
        """
        self._store.clear()

    def __repr__(self):
        """
        Return a string representation of the object.

        Returns:
            str: A string representation of the internal store.
        """
        return f"{self._store}"


def get_mfa_secret_store():
    """
    Get the MFA secret store instance.

    This function returns the module-level mfa_secret_store object that stores
    multi-factor authentication secrets.

    Returns:
        dict or object: The MFA secret store containing authentication secrets.
    """
    return mfa_secret_store


# Initialize a module-level MFA secret store instance
mfa_secret_store = MFASecretStore()
