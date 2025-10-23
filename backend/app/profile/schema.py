import time
import threading
from pydantic import BaseModel
import core.cryptography as core_cryptography
import core.logger as core_logger


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
    """
    Thread-safe in-memory store for temporary MFA secrets with automatic expiration.
    This class provides secure storage for Multi-Factor Authentication (MFA) secrets
    with automatic cleanup of expired entries. Secrets are encrypted using Fernet
    encryption and stored with a configurable time-to-live (TTL) period.
    Key Features:
        - Thread-safe operations using reentrant locks
        - Automatic encryption/decryption of secrets
        - Background cleanup thread for expired secrets
        - Configurable TTL for stored secrets
        - Statistics and monitoring capabilities
        _store (dict): Internal dictionary storing encrypted secrets in format
            {user_id: {"encrypted_secret": str, "expires_at": float}}
        _lock (threading.RLock): Reentrant lock for thread-safe operations
        _ttl_seconds (int): Time-to-live duration for secrets in seconds
        _cleanup_thread (threading.Thread): Background thread for automatic cleanup
        >>> store.add_secret(user_id=123, secret="JBSWY3DPEHPK3PXP")
        >>> secret = store.get_secret(user_id=123)
        >>> if secret:
        ...     print("Secret retrieved successfully")
        >>> store.delete_secret(user_id=123)
        - All secrets are automatically encrypted before storage
        - Expired secrets are cleaned up every 30 seconds by a background daemon thread
        - The cleanup thread will not prevent program exit
        - All operations are thread-safe and can be called from multiple threads
        All public methods are thread-safe and can be safely called from multiple
        threads concurrently.
    """

    def __init__(self, ttl_seconds: int = 300):
        """
        Initialize the TokenStore with a specified time-to-live for stored tokens.

        Args:
            ttl_seconds (int, optional): The number of seconds before a stored token expires. 
                Defaults to 300 (5 minutes).

        Attributes:
            _store (dict): Internal dictionary storing user tokens in the format 
                {user_id: {"encrypted_secret": str, "expires_at": float}}.
            _lock (threading.RLock): Reentrant lock to ensure thread-safe operations.
            _ttl_seconds (int): Time-to-live duration for tokens in seconds.
            _cleanup_thread: Thread object for automatic cleanup of expired tokens.
        """
        self._store = {}  # Format: {user_id: {"encrypted_secret": str, "expires_at": float}}
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        self._ttl_seconds = ttl_seconds
        self._cleanup_thread = None
        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        """
        Start a background cleanup thread for expired MFA secrets.

        This method creates and starts a daemon thread that runs the _cleanup_expired_secrets
        method. If a cleanup thread already exists and is still alive, no new thread is created.
        The thread is marked as a daemon so it will automatically terminate when the main program exits.

        The cleanup thread is stored in self._cleanup_thread for tracking purposes.

        Notes:
            - Only one cleanup thread will run at a time
            - The thread runs as a daemon and will not prevent program exit
            - Thread safety should be ensured in _cleanup_expired_secrets method
        """
        if self._cleanup_thread is None or not self._cleanup_thread.is_alive():
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_expired_secrets,
                daemon=True,
                name="MFA-Secret-Cleanup"
            )
            self._cleanup_thread.start()

    def _cleanup_expired_secrets(self):
        """
        Periodically clean up expired MFA secrets from the store.
        This method runs in an infinite loop as a background thread, checking for and
        removing expired secrets every 30 seconds. If an error occurs during cleanup,
        it logs the error and waits 60 seconds before retrying.
        The cleanup process:
        1. Gets the current timestamp
        2. Acquires a thread lock to safely access the store
        3. Identifies all user entries where the expiration time has passed
        4. Removes expired entries and logs each cleanup action
        5. Sleeps for 30 seconds (or 60 seconds on error) before repeating
        Note:
            This is designed to run as a daemon thread and will continue until
            the program terminates. All exceptions are caught and logged to prevent
            the cleanup thread from crashing.
        Raises:
            Does not raise exceptions; all errors are caught, logged, and handled internally.
        """
        while True:
            try:
                current_time = time.time()
                with self._lock:
                    expired_users = [
                        user_id for user_id, data in self._store.items()
                        if current_time > data["expires_at"]
                    ]
                    for user_id in expired_users:
                        del self._store[user_id]
                        core_logger.print_to_log(
                            f"Cleaned up expired MFA secret for user {user_id}",
                            "debug"
                        )
                
                time.sleep(30)
            except Exception as err:
                core_logger.print_to_log(
                    f"Error in MFA secret cleanup thread: {err}",
                    "error",
                    exc=err
                )
                time.sleep(60)

    def add_secret(self, user_id: int, secret: str) -> None:
        """
        Securely stores an encrypted MFA secret for a user with an expiration time.
        Args:
            user_id (int): The unique identifier of the user.
            secret (str): The MFA secret to be encrypted and stored.
        Raises:
            ValueError: If the secret encryption fails.
            Exception: If any other error occurs during the storage process.
        Returns:
            None
        Notes:
            - The secret is encrypted using Fernet encryption before storage.
            - The stored secret automatically expires after the configured TTL period.
            - Thread-safe operation is ensured using an internal lock.
        """
        try:
            encrypted_secret = core_cryptography.encrypt_token_fernet(secret)
            if not encrypted_secret:
                raise ValueError("Failed to encrypt MFA secret")
            
            expires_at = time.time() + self._ttl_seconds
            
            with self._lock:
                self._store[user_id] = {
                    "encrypted_secret": encrypted_secret,
                    "expires_at": expires_at
                }
            
            core_logger.print_to_log(
                f"Securely stored MFA secret for user {user_id} (expires in {self._ttl_seconds}s)",
                "debug"
            )
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to add MFA secret for user {user_id}: {err}",
                "error",
                exc=err
            )
            raise

    def get_secret(self, user_id: int) -> str | None:
        """
        Retrieve and decrypt the MFA secret for a specified user.
        This method performs the following operations:
        1. Checks if a secret exists for the given user_id
        2. Validates that the secret has not expired
        3. Decrypts and returns the secret if valid
        4. Removes expired secrets from the store
        5. Logs any errors that occur during retrieval
        Args:
            user_id (int): The unique identifier of the user whose MFA secret should be retrieved.
        Returns:
            str | None: The decrypted MFA secret if found and valid, None if the secret doesn't exist,
                        has expired, or an error occurred during retrieval.
        Thread Safety:
            This method is thread-safe and uses an internal lock to prevent concurrent access issues.
        Side Effects:
            - Expired secrets are automatically removed from the internal store
            - Logs debug messages when secrets expire
            - Logs error messages if retrieval fails
        """
        try:
            with self._lock:
                if user_id not in self._store:
                    return None
                
                data = self._store[user_id]
                
                # Check if expired
                if time.time() > data["expires_at"]:
                    del self._store[user_id]
                    core_logger.print_to_log(
                        f"MFA secret expired for user {user_id}",
                        "debug"
                    )
                    return None
                
                # Decrypt and return
                decrypted_secret = core_cryptography.decrypt_token_fernet(
                    data["encrypted_secret"]
                )
                return decrypted_secret
                
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to get MFA secret for user {user_id}: {err}",
                "error",
                exc=err
            )
            return None

    def delete_secret(self, user_id: int) -> None:
        """
        Securely deletes the MFA secret for a specified user from the store.

        This method removes the MFA secret associated with the given user ID from the internal
        store in a thread-safe manner using a lock. If the deletion fails, an error is logged.

        Args:
            user_id (int): The unique identifier of the user whose MFA secret should be deleted.

        Returns:
            None

        Raises:
            Does not raise exceptions directly; errors are caught and logged internally.

        Note:
            - If the user_id does not exist in the store, no action is taken.
            - All operations are protected by a thread lock to ensure thread safety.
            - Errors during deletion are logged using the core_logger.
        """
        try:
            with self._lock:
                if user_id in self._store:
                    del self._store[user_id]
                    core_logger.print_to_log(
                        f"Securely deleted MFA secret for user {user_id}",
                        "debug"
                    )
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to delete MFA secret for user {user_id}: {err}",
                "error",
                exc=err
            )

    def has_secret(self, user_id: int) -> bool:
        """
        Check if a user has a valid MFA secret stored.
        This method verifies whether a user has an MFA secret in the store and
        checks if it has expired. If the secret has expired, it is automatically
        removed from the store.
        Args:
            user_id (int): The unique identifier of the user to check.
        Returns:
            bool: True if the user has a valid (non-expired) MFA secret, 
                  False if the secret doesn't exist, has expired, or an error occurred.
        Raises:
            None: All exceptions are caught and logged internally.
        Thread Safety:
            This method is thread-safe and uses an internal lock to protect
            concurrent access to the store.
        """
        try:
            with self._lock:
                if user_id not in self._store:
                    return False
                
                # Check if expired
                if time.time() > self._store[user_id]["expires_at"]:
                    del self._store[user_id]
                    return False
                
                return True
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to check MFA secret for user {user_id}: {err}",
                "error",
                exc=err
            )
            return False

    def clear_all(self) -> None:
        """
        Clear all MFA secrets from the store.

        This method removes all stored MFA secrets from the internal store in a
        thread-safe manner. It logs the number of secrets cleared on success or
        logs an error if the operation fails.

        Raises:
            Exception: Logs any exception that occurs during the clear operation
                but does not re-raise it.

        Note:
            This method uses a lock to ensure thread-safety during the clear operation.
        """
        try:
            with self._lock:
                cleared_count = len(self._store)
                self._store.clear()
                core_logger.print_to_log(
                    f"Cleared {cleared_count} MFA secrets from store",
                    "info"
                )
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to clear MFA secret store: {err}",
                "error",
                exc=err
            )

    def get_stats(self) -> dict:
        """
        Retrieve statistics about the MFA secret store.
        This method provides information about the current state of the secret store,
        including the total number of secrets, how many have expired, and how many
        are still active.
        Returns:
            dict: A dictionary containing the following keys:
                - total_secrets (int): Total number of secrets in the store
                - expired_secrets (int): Number of secrets that have expired
                - active_secrets (int): Number of secrets that are still valid
                - ttl_seconds (int): The time-to-live value in seconds for secrets
                - error (str): Error message if an exception occurs (only present on error)
        Raises:
            No exceptions are raised; errors are caught and returned in the result dictionary.
        """
        try:
            with self._lock:
                current_time = time.time()
                total_count = len(self._store)
                expired_count = sum(
                    1 for data in self._store.values()
                    if current_time > data["expires_at"]
                )
                
                return {
                    "total_secrets": total_count,
                    "expired_secrets": expired_count,
                    "active_secrets": total_count - expired_count,
                    "ttl_seconds": self._ttl_seconds
                }
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to get MFA secret store stats: {err}",
                "error",
                exc=err
            )
            return {"error": str(err)}

    def __repr__(self) -> str:
        """
        Return a string representation of the MFASecretStore instance.

        Returns:
            str: A string showing the number of active secrets and the TTL (time-to-live) 
                 in seconds for the MFA secret store.

        Example:
            >>> store = MFASecretStore(ttl_seconds=300)
            >>> repr(store)
            'MFASecretStore(active=0, ttl=300s)'
        """
        stats = self.get_stats()
        return f"MFASecretStore(active={stats.get('active_secrets', 0)}, ttl={self._ttl_seconds}s)"


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
