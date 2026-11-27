"""
Tests for core.cryptography module.

Verifies:
1. Fernet cipher creation and error handling
2. Token encryption/decryption with various inputs
3. None value handling
4. Type conversion for non-string tokens
5. Error handling for invalid keys and malformed data
"""

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

import core.exceptions as core_exceptions
from core import cryptography


class TestCreateFernetCipher:
    """Tests for create_fernet_cipher function."""

    def test_create_fernet_cipher_success(self, monkeypatch):
        """Test successful Fernet cipher creation."""
        # Generate a valid Fernet key
        valid_key = Fernet.generate_key().decode()
        monkeypatch.setenv("FERNET_KEY", valid_key)

        cipher = cryptography.create_fernet_cipher()

        assert isinstance(cipher, MultiFernet)

    def test_create_fernet_cipher_missing_key(self, monkeypatch):
        """Test Fernet cipher creation fails when FERNET_KEY is missing."""
        # Remove FERNET_KEY from environment
        monkeypatch.delenv("FERNET_KEY", raising=False)
        monkeypatch.delenv("FERNET_KEY_FILE", raising=False)

        with patch("core.config.read_secret", return_value=None):
            with pytest.raises(core_exceptions.CryptographyError) as exc_info:
                cryptography.create_fernet_cipher()

            assert exc_info.value.status_code == 500
            assert exc_info.value.detail == "Internal Server Error"

    def test_create_fernet_cipher_invalid_key(self, monkeypatch):
        """Test Fernet cipher creation fails with invalid key."""
        monkeypatch.setenv("FERNET_KEY", "invalid_key")

        with pytest.raises(core_exceptions.CryptographyError) as exc_info:
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

        with pytest.raises(core_exceptions.CryptographyError) as exc_info:
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

        with pytest.raises(core_exceptions.UndecryptableError) as exc_info:
            cryptography.decrypt_token_fernet(invalid_encrypted)

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Internal Server Error"

    def test_decrypt_token_tampered_data(self):
        """Test decryption fails with tampered data."""
        original_token = "test_token_123"
        encrypted = cryptography.encrypt_token_fernet(original_token)

        # Tamper with the encrypted data
        tampered = encrypted[:-5] + "XXXXX"

        with pytest.raises(core_exceptions.UndecryptableError) as exc_info:
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
        with pytest.raises(core_exceptions.UndecryptableError) as exc_info:
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


class TestDecryptKeyFailure:
    """A key that cannot be used is not an undecryptable value."""

    def test_an_unusable_key_is_a_cryptography_error_not_an_undecryptable_value(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", "invalid_key")

        with pytest.raises(core_exceptions.CryptographyError) as exc_info:
            cryptography.decrypt_token_fernet("anything")

        assert not isinstance(exc_info.value, core_exceptions.UndecryptableError)


def _token(key: str, plaintext: str) -> str:
    """Encrypt ``plaintext`` under ``key`` alone."""
    return Fernet(key.encode()).encrypt(plaintext.encode()).decode()


class TestKeyList:
    """FERNET_KEY accepts a comma-separated list: the first key encrypts, every key decrypts."""

    def setup_method(self):
        self.new_key = Fernet.generate_key().decode()
        self.old_key = Fernet.generate_key().decode()

    def test_single_key_is_unchanged(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", self.new_key)

        encrypted = cryptography.encrypt_token_fernet("secret")

        assert Fernet(self.new_key.encode()).decrypt(encrypted.encode()) == b"secret"
        assert cryptography.has_older_keys() is False

    def test_first_key_encrypts(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", f"{self.new_key},{self.old_key}")

        encrypted = cryptography.encrypt_token_fernet("secret")

        assert Fernet(self.new_key.encode()).decrypt(encrypted.encode()) == b"secret"
        with pytest.raises(InvalidToken):
            Fernet(self.old_key.encode()).decrypt(encrypted.encode())

    def test_every_key_decrypts(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", f"{self.new_key},{self.old_key}")

        assert cryptography.decrypt_token_fernet(_token(self.new_key, "a")) == "a"
        assert cryptography.decrypt_token_fernet(_token(self.old_key, "b")) == "b"

    def test_whitespace_around_keys_is_trimmed(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", f"  {self.new_key} ,\n{self.old_key}  ")

        assert cryptography.decrypt_token_fernet(_token(self.old_key, "b")) == "b"
        assert cryptography.has_older_keys() is True

    @pytest.mark.parametrize("template", ["{new},", ",{new}", "{new},,{old}", "{new}, ,{old}"])
    def test_empty_entry_is_refused(self, monkeypatch, template):
        monkeypatch.setenv("FERNET_KEY", template.format(new=self.new_key, old=self.old_key))

        with pytest.raises(core_exceptions.CryptographyError):
            cryptography.create_fernet_cipher()

    def test_invalid_key_in_list_is_refused(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", f"{self.new_key},invalid_key")

        with pytest.raises(core_exceptions.CryptographyError):
            cryptography.create_fernet_cipher()


class TestReencryptToPrimaryKey:
    """reencrypt_to_primary_key moves a value from an older key to the first key."""

    def setup_method(self):
        self.new_key = Fernet.generate_key().decode()
        self.old_key = Fernet.generate_key().decode()

    def test_old_key_value_is_rewritten_under_first_key(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", f"{self.new_key},{self.old_key}")

        rewritten = cryptography.reencrypt_to_primary_key(_token(self.old_key, "secret"))

        assert rewritten is not None
        assert Fernet(self.new_key.encode()).decrypt(rewritten.encode()) == b"secret"

    def test_first_key_value_is_left_alone(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", f"{self.new_key},{self.old_key}")

        assert cryptography.reencrypt_to_primary_key(_token(self.new_key, "secret")) is None

    def test_undecryptable_value_raises(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", f"{self.new_key},{self.old_key}")

        with pytest.raises(core_exceptions.UndecryptableError):
            cryptography.reencrypt_to_primary_key(_token(Fernet.generate_key().decode(), "secret"))

    def test_garbage_value_raises(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", f"{self.new_key},{self.old_key}")

        with pytest.raises(core_exceptions.UndecryptableError):
            cryptography.reencrypt_to_primary_key("not-a-token")


class TestSameSecret:
    """same_secret compares what two stored secrets decrypt to."""

    def setup_method(self):
        self.new_key = Fernet.generate_key().decode()
        self.old_key = Fernet.generate_key().decode()

    def test_rewrapped_value_is_the_same_secret(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", f"{self.new_key},{self.old_key}")
        old = _token(self.old_key, "secret")
        new = cryptography.reencrypt_to_primary_key(old)

        assert new != old
        assert cryptography.same_secret(old, new) is True

    def test_different_values_differ(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", self.new_key)

        assert cryptography.same_secret(_token(self.new_key, "a"), _token(self.new_key, "b")) is False

    def test_none_handling(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", self.new_key)
        token = _token(self.new_key, "a")

        assert cryptography.same_secret(None, None) is True
        assert cryptography.same_secret(token, None) is False
        assert cryptography.same_secret(None, token) is False

    def test_undecryptable_value_is_not_the_same(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", self.new_key)
        stranger = _token(Fernet.generate_key().decode(), "a")

        assert cryptography.same_secret(stranger, stranger) is False
