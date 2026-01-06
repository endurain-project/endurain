import pytest
import re
import string
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from auth.password_hasher import PasswordHasher, PasswordPolicyError


class TestPasswordHasherSecurity:
    """
    Test suite for the PasswordHasher class and related password security functionality.

    This class contains comprehensive tests to ensure the correctness, security, and policy enforcement
    of password hashing, verification, password generation, and password validation logic. The tests cover:

    - Initialization of PasswordHasher with various types of hashers (None, single hasher, iterable, PasswordHash instance, incorrect types).
    - Hashing and verifying passwords, including correct, incorrect, case-sensitive, very long, and Unicode passwords.
    - Ensuring that password hashes are unique and non-empty.
    - Verifying and updating password hashes when algorithms change.
    - Password generation, including length requirements, character class inclusion, and uniqueness.
    - Password validation, enforcing policy requirements such as minimum length, presence of uppercase, lowercase, digits, and special characters.
    - Handling of edge cases such as empty passwords, whitespace-only passwords, and custom minimum length requirements.
    - Ensuring proper error handling and exception raising for invalid inputs and policy violations.

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

        assert hasher.verify(password, hashed), "Default hasher should work correctly"
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

        assert hasher.verify(
            password, hashed
        ), "PasswordHash instance should work correctly"

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

        assert hasher.verify(
            password, hashed
        ), "Iterable of hashers should work correctly"

    def test_password_hasher_initialization_with_iterable(self):
        """
        Test that PasswordHasher can be initialized with an iterable of hasher instances (such as a tuple),
        and that password hashing and verification work correctly with this configuration.
        """
        # Pass as a tuple (iterable that's not a list)
        hasher = PasswordHasher(hasher=(Argon2Hasher(), BcryptHasher()))

        password = "TestPassword123!"
        hashed = hasher.hash_password(password)

        assert hasher.verify(
            password, hashed
        ), "Iterable of hashers should work correctly"

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
            match="Unsupported hasher type.*Must be Argon2Hasher, BcryptHasher, Iterable, PasswordHash, or None",
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

        assert hasher.verify(
            password, hashed
        ), "Generic iterable (set) should work correctly"

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

        assert password_hasher.verify(
            password, hashed
        ), "Correct password should verify successfully"

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

        assert not password_hasher.verify(
            wrong_password, hashed
        ), "Incorrect password should fail verification"

    def test_verify_case_sensitivity(self, password_hasher):
        """
        Tests that the password verification is case-sensitive by ensuring that a password
        with different casing does not match the hashed password.
        """
        password = "TestPassword123!"
        hashed = password_hasher.hash_password(password)

        assert not password_hasher.verify(
            "testpassword123!", hashed
        ), "Password verification should be case-sensitive"

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
        assert (
            updated_hash is None
        ), "Updated hash should be None for current hash algorithm"

    def test_verify_and_update_with_incorrect_password(self, password_hasher):
        """
        Test that verify_and_update returns False when an incorrect password is provided.

        This test hashes a correct password, then attempts to verify and update the hash using an incorrect password.
        It asserts that the verification fails, ensuring that the password hasher does not validate incorrect credentials.
        """
        correct_password = "CorrectPassword123!"
        wrong_password = "WrongPassword123!"
        hashed = password_hasher.hash_password(correct_password)

        is_valid, _updated_hash = password_hasher.verify_and_update(
            wrong_password, hashed
        )

        assert not is_valid, "Incorrect password should not verify"

    def test_generate_password_meets_length_requirement(self, password_hasher):
        """
        Test that the `generate_password` method of the password_hasher generates passwords
        of the exact specified length for various input lengths.

        Args:
            password_hasher: An instance of the password hasher class with a `generate_password` method.

        Asserts:
            The generated password's length matches the requested length for each value in [8, 12, 16, 20].
        """
        lengths = [8, 12, 16, 20]
        for length in lengths:
            password = password_hasher.generate_password(length)
            assert (
                len(password) == length
            ), f"Generated password should be {length} characters long"

    def test_generate_password_has_required_character_classes(self, password_hasher):
        """
        Test that the password generated by the password_hasher contains at least one character from each required class:
        uppercase letters, lowercase letters, digits, and punctuation. Asserts that the generated password meets all these criteria.
        """
        password = password_hasher.generate_password(12)

        has_upper = any(c in string.ascii_uppercase for c in password)
        has_lower = any(c in string.ascii_lowercase for c in password)
        has_digit = any(c in string.digits for c in password)
        has_punct = any(c in string.punctuation for c in password)

        assert has_upper, "Generated password should contain uppercase letters"
        assert has_lower, "Generated password should contain lowercase letters"
        assert has_digit, "Generated password should contain digits"
        assert has_punct, "Generated password should contain punctuation"

    def test_generate_password_uniqueness(self, password_hasher):
        """
        Test that the `generate_password` method of the password hasher produces unique passwords
        for multiple invocations, ensuring cryptographic security by verifying that all generated
        passwords in a sample are distinct.
        """
        passwords = [password_hasher.generate_password(12) for _ in range(10)]
        unique_passwords = set(passwords)

        assert (
            len(unique_passwords) == 10
        ), "Generated passwords should be unique (cryptographically secure)"

    def test_validate_password_accepts_valid_password(self, password_hasher):
        """
        Test that the `validate_password` method of the password hasher accepts valid passwords.

        This test iterates over a list of valid passwords and asserts that none of them raise a
        PasswordPolicyError when passed to the `validate_password` method. If a valid password
        raises an error, the test fails with an appropriate message.
        """
        valid_passwords = [
            "ValidPass1!",
            "Str0ng!Pass",
            "C0mplex@Password",
            "Test123!Password",
        ]

        for password in valid_passwords:
            try:
                password_hasher.validate_password(password)
            except PasswordPolicyError:
                pytest.fail(
                    f"Valid password '{password}' should not raise PasswordPolicyError"
                )

    def test_validate_password_rejects_short_password(self, password_hasher):
        """
        Test that the password hasher's validate_password method raises a PasswordPolicyError
        when given a password that is too short, and verifies that the error message indicates
        the password length issue.
        """
        with pytest.raises(PasswordPolicyError) as exc_info:
            password_hasher.validate_password("Short1!")

        error_message = str(exc_info.value)
        assert re.search(
            r"too short", error_message, re.IGNORECASE
        ), f"Error should mention password is too short, got: {error_message}"

    def test_validate_password_rejects_missing_uppercase(self, password_hasher):
        """
        Test that `validate_password` raises a `PasswordPolicyError` with a message containing
        "uppercase letter" when the password does not contain any uppercase characters.
        """
        with pytest.raises(PasswordPolicyError, match="uppercase letter"):
            password_hasher.validate_password("lowercase123!")

    def test_validate_password_rejects_missing_lowercase(self, password_hasher):
        """
        Test that the password validator rejects passwords that do not contain any lowercase letters.

        This test ensures that when a password consisting only of uppercase letters, digits, and symbols
        is provided, the `validate_password` method raises a `PasswordPolicyError` with a message indicating
        the requirement for at least one lowercase letter.
        """
        with pytest.raises(PasswordPolicyError, match="lowercase letter"):
            password_hasher.validate_password("UPPERCASE123!")

    def test_validate_password_rejects_missing_digit(self, password_hasher):
        """
        Test that the password validation rejects passwords missing a digit.

        This test verifies that the `validate_password` method of the `password_hasher`
        raises a `PasswordPolicyError` with a message containing "digit" when the input
        password does not contain any numeric characters.
        """
        with pytest.raises(PasswordPolicyError, match="digit"):
            password_hasher.validate_password("NoDigitsHere!")

    def test_validate_password_rejects_missing_punctuation(self, password_hasher):
        """
        Test that the password validator rejects passwords that do not contain any special (punctuation) characters.

        This test ensures that when a password lacking special characters is validated,
        a PasswordPolicyError is raised with a message indicating the requirement for a special character.
        """
        with pytest.raises(PasswordPolicyError, match="special character"):
            password_hasher.validate_password("NoSpecialChars123")

    def test_validate_password_custom_min_length(self, password_hasher):
        """
        Test that the password validator enforces a custom minimum length requirement.

        This test verifies that when a password shorter than the specified `min_length` is validated,
        a `PasswordPolicyError` is raised and the error message correctly mentions the custom minimum length.
        """
        short_but_valid = "Ab1!"  # Valid, but short

        # Should fail with higher min_length
        with pytest.raises(PasswordPolicyError) as exc_info:
            password_hasher.validate_password(short_but_valid, min_length=10)

        error_message = str(exc_info.value)
        assert re.search(
            r"too short.*need ≥ 10", error_message, re.IGNORECASE
        ), f"Error should mention custom minimum length, got: {error_message}"

    def test_is_valid_password_returns_true_for_valid(self, password_hasher):
        """
        Tests that the is_valid_password method returns True when provided with a valid password.

        This test verifies that the password_hasher's is_valid_password function correctly identifies
        a valid password ("ValidPass123!") and returns True, ensuring that the password validation
        logic accepts passwords that meet the required criteria.
        """
        assert password_hasher.is_valid_password(
            "ValidPass123!"
        ), "Valid password should return True"

    def test_is_valid_password_returns_false_for_invalid(self, password_hasher):
        """
        Tests that the is_valid_password method of the password_hasher returns False for various
        invalid passwords.
        The test covers the following invalid cases:
        - Passwords that are too short
        - Passwords without uppercase letters
        - Passwords without lowercase letters
        - Passwords without digits
        - Passwords without special characters
        """
        invalid_passwords = [
            "short",  # Too short
            "nouppercase123!",  # No uppercase
            "NOLOWERCASE123!",  # No lowercase
            "NoDigitsHere!",  # No digits
            "NoSpecialChar123",  # No punctuation
        ]

        for password in invalid_passwords:
            assert not password_hasher.is_valid_password(
                password
            ), f"Invalid password '{password}' should return False"

    def test_empty_password_handling(self, password_hasher):
        """
        Test that the password hasher raises a PasswordPolicyError when validating an empty password.

        This test ensures that the password validation logic correctly identifies and rejects empty passwords,
        enforcing the password policy by raising the appropriate exception.
        """
        with pytest.raises(PasswordPolicyError):
            password_hasher.validate_password("")

    def test_whitespace_only_password(self, password_hasher):
        """
        Test that the password hasher raises a PasswordPolicyError when validating a password consisting only
        of whitespace characters.
        """
        with pytest.raises(PasswordPolicyError):
            password_hasher.validate_password("        ")

    def test_very_long_password(self, password_hasher):
        """
        Tests that the password hasher can correctly hash and verify a very long password (1003 characters).
        Ensures that both hashing and verification processes handle long input without errors or data loss.
        """
        long_password = "A1!" + "x" * 1000  # 1003 characters
        hashed = password_hasher.hash_password(long_password)
        assert password_hasher.verify(
            long_password, hashed
        ), "Very long passwords should hash and verify correctly"

    def test_unicode_characters_in_password(self, password_hasher):
        """
        Tests that the password hasher can correctly hash and verify passwords containing Unicode characters.
        Ensures that passwords with special or non-ASCII characters are supported and function as expected.
        """
        unicode_password = "Tëst123!Pāśswörd"
        hashed = password_hasher.hash_password(unicode_password)
        assert password_hasher.verify(
            unicode_password, hashed
        ), "Unicode passwords should hash and verify correctly"

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
            assert password_hasher.verify(
                password, hashed
            ), f"Special character password '{password}' should work correctly"

    def test_generate_password_length_too_short(self):
        """
        Test that PasswordHasher.generate_password raises a PasswordPolicyError when the requested password length is
        less than the minimum allowed (8 characters), and verifies that the error message indicates the password is
        too short and specifies the minimum length requirement.
        """
        with pytest.raises(PasswordPolicyError) as exc_info:
            PasswordHasher.generate_password(length=7)

        assert "too short" in str(exc_info.value).lower()
        assert "must be ≥ 8" in str(exc_info.value) or "must be >= 8" in str(
            exc_info.value
        )

    # Tests for policy_type parameter

    def test_validate_password_strict_policy_default(self, password_hasher):
        """
        Test that the default policy_type is 'strict' and enforces all complexity requirements.
        """
        # This should pass with strict policy (default)
        try:
            password_hasher.validate_password("ValidPass1!")
        except PasswordPolicyError:
            pytest.fail("Valid password should pass strict policy validation")

        # Missing uppercase should fail
        with pytest.raises(PasswordPolicyError, match="uppercase letter"):
            password_hasher.validate_password("lowercase123!")

    def test_validate_password_length_only_policy(self, password_hasher):
        """
        Test that 'length_only' policy only enforces minimum length, not complexity.
        """
        # Password with only lowercase letters should pass if it meets length
        try:
            password_hasher.validate_password(
                "simplelowercasepassword", min_length=8, policy_type="length_only"
            )
        except PasswordPolicyError:
            pytest.fail(
                "Simple password should pass length_only policy if it meets min_length"
            )

        # Password without special chars, uppercase, or digits should pass
        try:
            password_hasher.validate_password(
                "justlowercaseletters", min_length=8, policy_type="length_only"
            )
        except PasswordPolicyError:
            pytest.fail("Password without complexity should pass length_only policy")

    def test_validate_password_length_only_still_enforces_length(self, password_hasher):
        """
        Test that 'length_only' policy still enforces minimum length requirement.
        """
        with pytest.raises(PasswordPolicyError) as exc_info:
            password_hasher.validate_password(
                "short", min_length=8, policy_type="length_only"
            )

        assert "too short" in str(exc_info.value).lower()

    def test_validate_password_unknown_policy_raises_error(self, password_hasher):
        """
        Test that an unknown policy_type raises a PasswordPolicyError.
        """
        with pytest.raises(PasswordPolicyError) as exc_info:
            password_hasher.validate_password(
                "ValidPass1!", min_length=8, policy_type="unknown_policy"
            )

        error_message = str(exc_info.value)
        assert "unknown password policy type" in error_message.lower()
        assert "unknown_policy" in error_message

    def test_validate_password_strict_requires_all_character_classes(
        self, password_hasher
    ):
        """
        Test that 'strict' policy requires all character classes (uppercase, lowercase, digit, special).
        """
        test_cases = [
            ("onlylowercase", "uppercase letter"),
            ("ONLYUPPERCASE", "lowercase letter"),
            ("NoDigitsHere!", "digit"),
            ("NoSpecialChar123", "special character"),
        ]

        for password, expected_error in test_cases:
            with pytest.raises(PasswordPolicyError, match=expected_error):
                password_hasher.validate_password(
                    password, min_length=8, policy_type="strict"
                )

    def test_is_valid_password_with_length_only_policy(self, password_hasher):
        """
        Test that is_valid_password works correctly with 'length_only' policy.
        """
        # Simple password should be valid with length_only policy
        assert password_hasher.is_valid_password(
            "simplelowercase", min_length=8, policy_type="length_only"
        ), "Simple password should be valid with length_only policy"

        # Short password should still be invalid
        assert not password_hasher.is_valid_password(
            "short", min_length=8, policy_type="length_only"
        ), "Short password should be invalid even with length_only policy"

    def test_validate_password_with_custom_min_length_and_policy(self, password_hasher):
        """
        Test that custom min_length works correctly with different policies.
        """
        # 15-character passphrase with length_only should pass with min_length=12
        try:
            password_hasher.validate_password(
                "mysimplepassphrase", min_length=12, policy_type="length_only"
            )
        except PasswordPolicyError:
            pytest.fail(
                "Passphrase should pass with length_only policy and min_length=12"
            )

        # Same passphrase should fail with min_length=20
        with pytest.raises(PasswordPolicyError) as exc_info:
            password_hasher.validate_password(
                "mysimplepassphrase", min_length=20, policy_type="length_only"
            )

        assert "too short" in str(exc_info.value).lower()
        assert "≥ 20" in str(exc_info.value) or ">= 20" in str(exc_info.value)

    def test_validate_password_passphrase_use_case(self, password_hasher):
        """
        Test the passphrase use case: long password without complexity requirements.
        This is the main use case that prompted the policy_type feature.
        """
        passphrase = "correct horse battery staple"  # 28 characters

        # Should fail with strict policy (no uppercase, digit, special char)
        with pytest.raises(PasswordPolicyError):
            password_hasher.validate_password(
                passphrase, min_length=8, policy_type="strict"
            )

        # Should pass with length_only policy
        try:
            password_hasher.validate_password(
                passphrase, min_length=16, policy_type="length_only"
            )
        except PasswordPolicyError:
            pytest.fail("Passphrase should pass with length_only policy")
