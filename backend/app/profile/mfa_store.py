"""Thread-safe temporary MFA secret storage with TTL.

This module provides secure, encrypted storage for MFA secrets
during the setup flow with automatic expiration and cleanup.

Key Features:
- Thread-safe operations with RLock
- Encrypted storage using Fernet
- Automatic TTL-based expiration
- Background cleanup thread
"""

import time
import threading
import core.cryptography as core_cryptography
import core.logger as core_logger


class MFASecretStore:
    """
    Thread-safe storage for temporary MFA secrets with TTL.

    Attributes:
        _store: Internal storage for encrypted secrets.
        _lock: Thread synchronization lock.
        _ttl_seconds: Time-to-live for stored secrets.
        _cleanup_thread: Background thread for cleanup.
    """

    def __init__(self, ttl_seconds: int = 300):
        """
        Initialize the MFA secret store.

        Args:
            ttl_seconds: Time-to-live for secrets in seconds.
        """
        self._store = (
            {}
        )  # Format: {user_id: {"encrypted_secret": str, "expires_at": float}}
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        self._ttl_seconds = ttl_seconds
        self._cleanup_thread = None
        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        """
        Start the background cleanup thread if not running.
        """
        if self._cleanup_thread is None or not self._cleanup_thread.is_alive():
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_expired_secrets,
                daemon=True,
                name="MFA-Secret-Cleanup",
            )
            self._cleanup_thread.start()

    def _cleanup_expired_secrets(self):
        """
        Continuously remove expired secrets from storage.
        """
        while True:
            try:
                current_time = time.time()
                with self._lock:
                    expired_users = [
                        user_id
                        for user_id, data in self._store.items()
                        if current_time > data["expires_at"]
                    ]
                    for user_id in expired_users:
                        del self._store[user_id]
                        core_logger.print_to_log(
                            f"Cleaned up expired MFA secret for user {user_id}", "debug"
                        )

                time.sleep(30)
            except Exception as err:
                core_logger.print_to_log(
                    f"Error in MFA secret cleanup thread: {err}", "error", exc=err
                )
                time.sleep(60)

    def add_secret(self, user_id: int, secret: str) -> None:
        """
        Store an encrypted MFA secret with expiration.

        Args:
            user_id: The user ID to associate with the secret.
            secret: The plaintext MFA secret to encrypt and store.

        Raises:
            ValueError: If encryption fails.
            Exception: If storage operation fails.
        """
        try:
            encrypted_secret = core_cryptography.encrypt_token_fernet(secret)
            if not encrypted_secret:
                raise ValueError("Failed to encrypt MFA secret")

            expires_at = time.time() + self._ttl_seconds

            with self._lock:
                self._store[user_id] = {
                    "encrypted_secret": encrypted_secret,
                    "expires_at": expires_at,
                }

            core_logger.print_to_log(
                f"Securely stored MFA secret for user {user_id} (expires in {self._ttl_seconds}s)",
                "debug",
            )
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to add MFA secret for user {user_id}: {err}", "error", exc=err
            )
            raise

    def get_secret(self, user_id: int) -> str | None:
        """
        Retrieve and decrypt an MFA secret if not expired.

        Args:
            user_id: The user ID to retrieve the secret for.

        Returns:
            The decrypted MFA secret, or None if not found or
            expired.
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
                        f"MFA secret expired for user {user_id}", "debug"
                    )
                    return None

                # Decrypt and return
                decrypted_secret = core_cryptography.decrypt_token_fernet(
                    data["encrypted_secret"]
                )
                return decrypted_secret

        except Exception as err:
            core_logger.print_to_log(
                f"Failed to get MFA secret for user {user_id}: {err}", "error", exc=err
            )
            return None

    def delete_secret(self, user_id: int) -> None:
        """
        Remove an MFA secret from storage.

        Args:
            user_id: The user ID whose secret to delete.
        """
        try:
            with self._lock:
                if user_id in self._store:
                    del self._store[user_id]
                    core_logger.print_to_log(
                        f"Securely deleted MFA secret for user {user_id}", "debug"
                    )
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to delete MFA secret for user {user_id}: {err}",
                "error",
                exc=err,
            )

    def has_secret(self, user_id: int) -> bool:
        """
        Check if a non-expired secret exists for a user.

        Args:
            user_id: The user ID to check.

        Returns:
            True if a valid secret exists, False otherwise.
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
                exc=err,
            )
            return False

    def clear_all(self) -> None:
        """
        Remove all MFA secrets from storage.
        """
        try:
            with self._lock:
                cleared_count = len(self._store)
                self._store.clear()
                core_logger.print_to_log(
                    f"Cleared {cleared_count} MFA secrets from store", "info"
                )
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to clear MFA secret store: {err}", "error", exc=err
            )

    def get_stats(self) -> dict:
        """
        Get statistics about the secret store.

        Returns:
            Dictionary with total, expired, and active secret
            counts.
        """
        try:
            with self._lock:
                current_time = time.time()
                total_count = len(self._store)
                expired_count = sum(
                    1
                    for data in self._store.values()
                    if current_time > data["expires_at"]
                )

                return {
                    "total_secrets": total_count,
                    "expired_secrets": expired_count,
                    "active_secrets": total_count - expired_count,
                    "ttl_seconds": self._ttl_seconds,
                }
        except Exception as err:
            core_logger.print_to_log(
                f"Failed to get MFA secret store stats: {err}", "error", exc=err
            )
            return {"error": str(err)}

    def __repr__(self) -> str:
        """
        Return a string representation of the store.

        Returns:
            String showing active secrets and TTL.
        """
        stats = self.get_stats()
        return f"MFASecretStore(active={stats.get('active_secrets', 0)}, ttl={self._ttl_seconds}s)"


def get_mfa_secret_store():
    """
    Get the module-level MFA secret store instance.

    Returns:
        The global MFASecretStore instance.
    """
    return mfa_secret_store


# Initialize a module-level MFA secret store instance
mfa_secret_store = MFASecretStore()
