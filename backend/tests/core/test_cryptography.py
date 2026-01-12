"""
Tests for core.cryptography module.

Verifies:
1. Fernet cipher creation and error handling
2. Token encryption/decryption with various inputs
3. None value handling
4. Type conversion for non-string tokens
5. Error handling for invalid keys and malformed data
"""

import os
import pytest
from unittest.mock import patch, MagicMock
from cryptography.fernet import Fernet
from fastapi import HTTPException

from core import cryptography


class TestCreateFernetCipher:
    """Tests for create_fernet_cipher function."""

    def test_create_fernet_cipher_success(self, monkeypatch):
        """Test successful Fernet cipher creation."""
        # Generate a valid Fernet key
        valid_key = Fernet.generate_key().decode()
        monkeypatch.setenv("FERNET_KEY", valid_key)

        cipher = cryptography.create_fernet_cipher()

        assert isinstance(cipher, Fernet)

    def test_create_fernet_cipher_missing_key(self, monkeypatch):
        """Test Fernet cipher creation fails when FERNET_KEY is missing."""
        # Remove FERNET_KEY from environment
        monkeypatch.delenv("FERNET_KEY", raising=False)
        monkeypatch.delenv("FERNET_KEY_FILE", raising=False)

        with patch("core.config.read_secret", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                cryptography.create_fernet_cipher()

            assert exc_info.value.status_code == 500
            assert exc_info.value.detail == "Internal Server Error"

    def test_create_fernet_cipher_invalid_key(self, monkeypatch):
        """Test Fernet cipher creation fails with invalid key."""
        monkeypatch.setenv("FERNET_KEY", "invalid_key")

        with pytest.raises(HTTPException) as exc_info:
            cryptography.create_fernet_cipher()

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Internal Server Error"


class TestEncryptTokenFernet:
    """Tests for encrypt_token_fernet function."""

    @pytest.fixture(autouse=True)
    def setup_valid_key(self, monkeypatch):
        """Setup a valid Fernet key for all tests."""
        self.valid_key = Fernet.generate_key().decode()
        monkeypatch.setenv("FERNET_KEY", self.valid_key)

    def test_encrypt_token_string(self):
        """Test encrypting a string token."""
        token = "test_token_123"

        encrypted = cryptography.encrypt_token_fernet(token)

        assert encrypted is not None
        assert isinstance(encrypted, str)
        assert encrypted != token  # Should be different from original

    def test_encrypt_token_integer(self):
        """Test encrypting an integer token (converted to string)."""
        token = 12345

        encrypted = cryptography.encrypt_token_fernet(token)

        assert encrypted is not None
        assert isinstance(encrypted, str)

    def test_encrypt_token_none(self):
        """Test encrypting None returns None."""
        encrypted = cryptography.encrypt_token_fernet(None)

        assert encrypted is None

    def test_encrypt_token_empty_string(self):
        """Test encrypting empty string."""
        encrypted = cryptography.encrypt_token_fernet("")

        assert encrypted is not None
        assert isinstance(encrypted, str)

    def test_encrypt_token_unicode(self):
        """Test encrypting unicode characters."""
        token = "test_token_🔒_unicode_ñ"

        encrypted = cryptography.encrypt_token_fernet(token)

        assert encrypted is not None
        assert isinstance(encrypted, str)

    def test_encrypt_token_long_string(self):
        """Test encrypting a long string."""
        token = "a" * 10000

        encrypted = cryptography.encrypt_token_fernet(token)

        assert encrypted is not None
        assert isinstance(encrypted, str)

    def test_encrypt_token_with_cipher_error(self, monkeypatch):
        """Test encryption fails gracefully when cipher creation fails."""
        monkeypatch.setenv("FERNET_KEY", "invalid_key")

        with pytest.raises(HTTPException) as exc_info:
            cryptography.encrypt_token_fernet("test")

        assert exc_info.value.status_code == 500


class TestDecryptTokenFernet:
    """Tests for decrypt_token_fernet function."""

    @pytest.fixture(autouse=True)
    def setup_valid_key(self, monkeypatch):
        """Setup a valid Fernet key for all tests."""
        self.valid_key = Fernet.generate_key().decode()
        monkeypatch.setenv("FERNET_KEY", self.valid_key)

    def test_decrypt_token_success(self):
        """Test successful token decryption."""
        original_token = "test_token_123"
        encrypted = cryptography.encrypt_token_fernet(original_token)

        decrypted = cryptography.decrypt_token_fernet(encrypted)

        assert decrypted == original_token

    def test_decrypt_token_none(self):
        """Test decrypting None returns None."""
        decrypted = cryptography.decrypt_token_fernet(None)

        assert decrypted is None

    def test_decrypt_token_invalid_encrypted_data(self):
        """Test decryption fails with invalid encrypted data."""
        invalid_encrypted = "not_a_valid_encrypted_token"

        with pytest.raises(HTTPException) as exc_info:
            cryptography.decrypt_token_fernet(invalid_encrypted)

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Internal Server Error"

    def test_decrypt_token_tampered_data(self):
        """Test decryption fails with tampered data."""
        original_token = "test_token_123"
        encrypted = cryptography.encrypt_token_fernet(original_token)

        # Tamper with the encrypted data
        tampered = encrypted[:-5] + "XXXXX"

        with pytest.raises(HTTPException) as exc_info:
            cryptography.decrypt_token_fernet(tampered)

        assert exc_info.value.status_code == 500

    def test_decrypt_token_unicode(self):
        """Test decrypting unicode characters."""
        original_token = "test_token_🔒_unicode_ñ"
        encrypted = cryptography.encrypt_token_fernet(original_token)

        decrypted = cryptography.decrypt_token_fernet(encrypted)

        assert decrypted == original_token

    def test_decrypt_token_empty_string(self):
        """Test decrypting empty string."""
        encrypted = cryptography.encrypt_token_fernet("")

        decrypted = cryptography.decrypt_token_fernet(encrypted)

        assert decrypted == ""

    def test_decrypt_with_different_key(self, monkeypatch):
        """Test decryption fails when using different key."""
        # Encrypt with first key
        original_token = "test_token_123"
        encrypted = cryptography.encrypt_token_fernet(original_token)

        # Change to different key
        new_key = Fernet.generate_key().decode()
        monkeypatch.setenv("FERNET_KEY", new_key)

        # Decryption should fail
        with pytest.raises(HTTPException) as exc_info:
            cryptography.decrypt_token_fernet(encrypted)

        assert exc_info.value.status_code == 500


class TestEncryptDecryptRoundtrip:
    """Tests for encrypt/decrypt roundtrip operations."""

    @pytest.fixture(autouse=True)
    def setup_valid_key(self, monkeypatch):
        """Setup a valid Fernet key for all tests."""
        self.valid_key = Fernet.generate_key().decode()
        monkeypatch.setenv("FERNET_KEY", self.valid_key)

    @pytest.mark.parametrize(
        "token",
        [
            "simple_token",
            "token_with_special_chars_!@#$%^&*()",
            "12345",
            "token-with-dashes",
            "token.with.dots",
            "token/with/slashes",
            "a" * 1000,  # Long token
        ],
    )
    def test_encrypt_decrypt_various_tokens(self, token):
        """Test encrypt/decrypt roundtrip for various token formats."""
        encrypted = cryptography.encrypt_token_fernet(token)
        decrypted = cryptography.decrypt_token_fernet(encrypted)

        assert decrypted == token

    def test_encrypt_decrypt_multiple_times(self):
        """Test that multiple encryptions produce different results but decrypt correctly."""
        token = "test_token"

        encrypted1 = cryptography.encrypt_token_fernet(token)
        encrypted2 = cryptography.encrypt_token_fernet(token)

        # Different encryptions should produce different results (Fernet includes timestamp)
        assert encrypted1 != encrypted2

        # Both should decrypt to the same original token
        assert cryptography.decrypt_token_fernet(encrypted1) == token
        assert cryptography.decrypt_token_fernet(encrypted2) == token
