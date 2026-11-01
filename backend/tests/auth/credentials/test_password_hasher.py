import pytest
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from modules.auth.credentials.password_hasher import PasswordHasher


class TestPasswordHasherSecurity:
    """
    Test suite for the PasswordHasher class and related password security functionality.

    This class contains tests to ensure the correctness and security of password hashing and verification. The
    password policy lives in ``password_policy`` and is tested in ``test_password_policy``. The tests cover:

    - Initialization of PasswordHasher with various types of hashers (None, single hasher, iterable, PasswordHash instance, incorrect types).
    - Hashing and verifying passwords, including correct, incorrect, case-sensitive, very long, and Unicode passwords.
    - Ensuring that password hashes are unique and non-empty.
    - Verifying and updating password hashes when algorithms change.

    Each test asserts the expected behavior and error handling to guarantee robust password security mechanisms.
    """

    def test_password_hasher_initialization_with_none(self):
        """
        Test that initializing PasswordHasher with None as the hasher uses the default hasher implementation.
        Verifies that hashing and verifying a password works correctly and that the resulting hash is not empty.
        """
        hasher = PasswordHasher(hasher=None)
        password = "TestPassword123!"
        hashed = hasher.hash_password(password)

        assert hasher.verify_password(password, hashed), "Default hasher should work correctly"
        assert len(hashed) > 0, "Hash should not be empty"

    def test_password_hasher_initialization_with_passwordhash_instance(self):
        """
        Test that the PasswordHasher can be initialized with a PasswordHash instance and
        correctly hash and verify a password using the provided hasher(s).
        Steps:
        - Create a PasswordHash instance with an Argon2Hasher.
        - Initialize PasswordHasher with the PasswordHash instance.
        - Hash a sample password.
        - Verify that the original password matches the hashed value.
        Asserts:
        - The password verification should succeed, confirming that the PasswordHash instance
            works as expected when passed to PasswordHasher.
        """
        # Create a PasswordHash instance
        pw_hash = PasswordHash([Argon2Hasher()])
        hasher = PasswordHasher(hasher=pw_hash)

        password = "TestPassword123!"
        hashed = hasher.hash_password(password)

        assert hasher.verify_password(password, hashed), "PasswordHash instance should work correctly"

    def test_password_hasher_initialization_with_single_hasher(self):
        """
        Tests the initialization of the PasswordHasher with a single hasher instance.

        This test verifies that:
        - A PasswordHasher can be initialized with a single Argon2Hasher.
        - The hasher can successfully hash a password.
        - The hasher can verify the password against the hashed value, ensuring correct functionality when using an iterable of hashers.
        """
        # Create a PasswordHash instance with a single hasher
        hasher = PasswordHasher(hasher=Argon2Hasher())

        password = "TestPassword123!"
        hashed = hasher.hash_password(password)

        assert hasher.verify_password(password, hashed), "Iterable of hashers should work correctly"

    def test_password_hasher_initialization_with_iterable(self):
        """
        Test that PasswordHasher can be initialized with an iterable of hasher instances (such as a tuple),
        and that password hashing and verification work correctly with this configuration.
        """
        # Pass as a tuple (iterable that's not a list)
        hasher = PasswordHasher(hasher=(Argon2Hasher(), BcryptHasher()))

        password = "TestPassword123!"
        hashed = hasher.hash_password(password)

        assert hasher.verify_password(password, hashed), "Iterable of hashers should work correctly"

    def test_password_hasher_initialization_with_incorrect_type(self):
        """
        Test that initializing PasswordHasher with an unsupported type (e.g., integer) raises a TypeError.

        This test verifies that passing a non-iterable and unsupported type as the `hasher` argument to
        PasswordHasher triggers a TypeError with the expected error message, ensuring type safety and
        proper error handling during initialization.
        """
        # Integers are not iterable and not supported types, so this should raise TypeError
        with pytest.raises(
            TypeError,
            match=r"Unsupported hasher type.*Must be Argon2Hasher, BcryptHasher, Iterable, PasswordHash, or None",
        ):
            PasswordHasher(hasher=12345)

    def test_password_hasher_initialization_with_generic_iterable(self):
        """
        Test that PasswordHasher can be initialized with a generic iterable (such as a set)
        of hasher instances, and that it correctly hashes and verifies a password using
        the provided hashers. Ensures that non-list/tuple iterables are properly handled.
        """
        # Use a set (which is iterable but not a list or tuple)
        # This will go through the generic Iterable path and call list(hasher)
        hasher_set = {Argon2Hasher(), BcryptHasher()}
        hasher = PasswordHasher(hasher=hasher_set)

        password = "TestPassword123!"
        hashed = hasher.hash_password(password)

        assert hasher.verify_password(password, hashed), "Generic iterable (set) should work correctly"

    def test_hash_password_produces_different_hashes(self, password_hasher):
        """
        Tests that hashing the same password multiple times produces different hashes,
        ensuring that the password hasher uses a random salt or similar mechanism.
        Also verifies that the generated hashes are not empty.
        """
        password = "TestPassword123!"
        hash1 = password_hasher.hash_password(password)
        hash2 = password_hasher.hash_password(password)

        assert hash1 != hash2, "Same password should produce different hashes"
        assert len(hash1) > 0, "Hash should not be empty"
        assert len(hash2) > 0, "Hash should not be empty"

    def test_verify_correct_password(self, password_hasher):
        """
        Tests that the password hasher correctly verifies a valid password.

        This test hashes a known password and then verifies that the original password
        is successfully validated against the generated hash. It asserts that the
        verification returns True, indicating that the password hasher works as expected
        for correct passwords.
        """
        password = "CorrectPassword123!"
        hashed = password_hasher.hash_password(password)

        assert password_hasher.verify_password(password, hashed), "Correct password should verify successfully"

    def test_verify_incorrect_password(self, password_hasher):
        """
        Test that verifying an incorrect password against a hashed correct password fails.

        This test ensures that the password hasher does not validate a wrong password,
        even if it is similar to the correct one. It hashes a known correct password,
        then attempts to verify a different, incorrect password against the hash,
        expecting the verification to fail.
        """
        correct_password = "CorrectPassword123!"
        wrong_password = "WrongPassword123!"
        hashed = password_hasher.hash_password(correct_password)

        assert not password_hasher.verify_password(wrong_password, hashed), (
            "Incorrect password should fail verification"
        )

    def test_verify_case_sensitivity(self, password_hasher):
        """
        Tests that the password verification is case-sensitive by ensuring that a password
        with different casing does not match the hashed password.
        """
        password = "TestPassword123!"
        hashed = password_hasher.hash_password(password)

        assert not password_hasher.verify_password("testpassword123!", hashed), (
            "Password verification should be case-sensitive"
        )

    def test_verify_and_update_returns_none_for_current_hash(self, password_hasher):
        """
        Tests that the `verify_and_update` method returns `None` for the updated hash
        when the provided password is hashed with the current algorithm.

        This ensures that if the password hash is already up-to-date with the latest
        hashing algorithm, no rehashing or hash update is performed.

        Args:
            password_hasher: An instance of the password hasher to be tested.

        Asserts:
            - The password is verified successfully.
            - The updated hash is None, indicating no update is needed for the current hash algorithm.
        """
        password = "TestPassword123!"
        hashed = password_hasher.hash_password(password)

        is_valid, updated_hash = password_hasher.verify_and_update(password, hashed)

        assert is_valid, "Password should verify successfully"
        assert updated_hash is None, "Updated hash should be None for current hash algorithm"

    def test_verify_and_update_with_incorrect_password(self, password_hasher):
        """
        Test that verify_and_update returns False when an incorrect password is provided.

        This test hashes a correct password, then attempts to verify and update the hash using an incorrect password.
        It asserts that the verification fails, ensuring that the password hasher does not validate incorrect credentials.
        """
        correct_password = "CorrectPassword123!"
        wrong_password = "WrongPassword123!"
        hashed = password_hasher.hash_password(correct_password)

        is_valid, _updated_hash = password_hasher.verify_and_update(wrong_password, hashed)

        assert not is_valid, "Incorrect password should not verify"

    def test_very_long_password(self, password_hasher):
        """
        Tests that the password hasher can correctly hash and verify a very long password (1003 characters).
        Ensures that both hashing and verification processes handle long input without errors or data loss.
        """
        long_password = "A1!" + "x" * 1000  # 1003 characters
        hashed = password_hasher.hash_password(long_password)
        assert password_hasher.verify_password(long_password, hashed), (
            "Very long passwords should hash and verify correctly"
        )

    def test_unicode_characters_in_password(self, password_hasher):
        """
        Tests that the password hasher can correctly hash and verify passwords containing Unicode characters.
        Ensures that passwords with special or non-ASCII characters are supported and function as expected.
        """
        unicode_password = "Tëst123!Pāśswörd"
        hashed = password_hasher.hash_password(unicode_password)
        assert password_hasher.verify_password(unicode_password, hashed), (
            "Unicode passwords should hash and verify correctly"
        )

    def test_special_characters_in_password(self, password_hasher):
        """
        Tests that the password hasher correctly handles passwords containing special characters.
        Verifies that passwords with various special characters can be hashed and subsequently verified successfully.
        """
        special_passwords = [
            "Test!@#$123",
            "Pass%^&*()456",
            "Word[]{}789",
            "Secure<>?:012",
        ]

        for password in special_passwords:
            hashed = password_hasher.hash_password(password)
            assert password_hasher.verify_password(password, hashed), (
                f"Special character password '{password}' should work correctly"
            )
