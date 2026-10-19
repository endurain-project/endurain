"""Tests for MFA backup codes utilities."""

import string
from unittest.mock import MagicMock, patch

import modules.auth.mfa.backup_codes.crud as backup_crud
import modules.auth.mfa.backup_codes.utils as backup_utils


class TestGenerateBackupCode:
    """Test suite for generate_backup_code function."""

    def test_generate_backup_code_format(self):
        """Test that generated code has correct format (XXXX-XXXX)."""
        code = backup_utils.generate_backup_code()

        assert len(code) == 9, "Code should be 9 characters (8 + 1 dash)"
        assert code[4] == "-", "Character at position 4 should be dash"
        assert code[:4].isalnum(), "First 4 characters should be alphanumeric"
        assert code[5:].isalnum(), "Last 4 characters should be alphanumeric"
        assert code.isupper(), "Code should be uppercase"

    def test_generate_backup_code_no_ambiguous_chars(self):
        """Test that generated codes don't contain ambiguous characters."""
        ambiguous_chars = {"0", "O", "1", "I"}

        # Generate multiple codes to test randomness
        for _ in range(100):
            code = backup_utils.generate_backup_code().replace("-", "")
            for char in code:
                assert char not in ambiguous_chars, f"Code contains ambiguous character: {char}"

    def test_generate_backup_code_uniqueness(self):
        """Test that generated codes are unique."""
        codes = [backup_utils.generate_backup_code() for _ in range(100)]

        # All codes should be unique (extremely high probability)
        assert len(set(codes)) == 100, "Generated codes should be unique"

    def test_generate_backup_code_character_set(self):
        """Test that generated codes only use allowed characters."""
        allowed_chars = set(string.ascii_uppercase + string.digits) - {
            "0",
            "O",
            "1",
            "I",
        }

        for _ in range(50):
            code = backup_utils.generate_backup_code().replace("-", "")
            for char in code:
                assert char in allowed_chars, f"Invalid character in code: {char}"


class TestVerifyAndConsumeBackupCode:
    """Test suite for verify_and_consume_backup_code function."""

    def test_verify_valid_code_success(self, mock_db, password_hasher):
        """Test successful verification of valid backup code."""
        # Arrange
        user_id = 1
        code = "A3K97BDF"

        mock_code_obj = MagicMock()
        mock_code_obj.code_hash = password_hasher.hash_password(code)
        mock_code_obj.used = False

        with (
            patch.object(backup_crud, "get_user_unused_backup_codes", return_value=[mock_code_obj]),
            patch.object(backup_crud, "mark_backup_code_as_used") as mock_mark_used,
        ):
            # Act
            result = backup_utils.verify_and_consume_backup_code(user_id, code, password_hasher, mock_db)

            # Assert
            assert result is True
            mock_mark_used.assert_called_once_with(mock_code_obj.id, user_id, mock_db)

    def test_verify_invalid_code_failure(self, mock_db, password_hasher):
        """Test verification fails with invalid code."""
        # Arrange
        user_id = 1
        correct_code = "A3K97BDF"
        wrong_code = "WRONGCOD"

        mock_code_obj = MagicMock()
        mock_code_obj.code_hash = password_hasher.hash_password(correct_code)
        mock_code_obj.used = False

        with (
            patch.object(backup_crud, "get_user_unused_backup_codes", return_value=[mock_code_obj]),
            patch.object(backup_crud, "mark_backup_code_as_used") as mock_mark_used,
        ):
            # Act
            result = backup_utils.verify_and_consume_backup_code(user_id, wrong_code, password_hasher, mock_db)

            # Assert
            assert result is False
            mock_mark_used.assert_not_called()

    def test_verify_no_unused_codes(self, mock_db, password_hasher):
        """Test verification fails when no unused codes exist."""
        # Arrange
        user_id = 1
        code = "A3K97BDF"

        with (
            patch.object(backup_crud, "get_user_unused_backup_codes", return_value=[]),
            patch.object(backup_crud, "mark_backup_code_as_used") as mock_mark_used,
        ):
            # Act
            result = backup_utils.verify_and_consume_backup_code(user_id, code, password_hasher, mock_db)

            # Assert
            assert result is False
            mock_mark_used.assert_not_called()

    def test_verify_multiple_codes_finds_match(self, mock_db, password_hasher):
        """Test verification finds correct code among multiple codes."""
        # Arrange
        user_id = 1
        correct_code = "CORRECT9"

        mock_codes = []
        for code_str in ["WRONG111", "WRONG222", correct_code, "WRONG333"]:
            mock_code = MagicMock()
            mock_code.code_hash = password_hasher.hash_password(code_str)
            mock_code.used = False
            mock_codes.append(mock_code)

        with (
            patch.object(backup_crud, "get_user_unused_backup_codes", return_value=mock_codes),
            patch.object(backup_crud, "mark_backup_code_as_used") as mock_mark_used,
        ):
            # Act
            result = backup_utils.verify_and_consume_backup_code(user_id, correct_code, password_hasher, mock_db)

            # Assert
            assert result is True
            mock_mark_used.assert_called_once()

    def test_verify_does_not_short_circuit_on_first_match(self, mock_db):
        """Verification must check every code regardless of match position.

        This guards the constant-time-equivalent property: the number of
        password verifications must not depend on where (or whether) a match
        is found, so an attacker cannot infer remaining-code count or match
        position from response latency.
        """
        # Arrange: the FIRST code is the valid one. A short-circuiting
        # implementation would verify only once; the hardened version must
        # still verify all four hashes.
        user_id = 1
        correct_code = "CORRECT9"
        codes_in_order = [correct_code, "WRONG111", "WRONG222", "WRONG333"]

        mock_codes = []
        for index, code_str in enumerate(codes_in_order):
            mock_code = MagicMock()
            mock_code.id = index + 1
            mock_code.code_hash = f"hash-for-{code_str}"
            mock_code.used = False
            mock_codes.append(mock_code)

        # A verifier that returns True only for the matching hash and counts
        # how many times it was invoked.
        verify_calls: list[str] = []

        class CountingVerifier:
            def verify_password(self, candidate: str, password_hash: str) -> bool:
                verify_calls.append(password_hash)
                return password_hash == f"hash-for-{candidate}"

        verifier = CountingVerifier()

        with (
            patch.object(backup_crud, "get_user_unused_backup_codes", return_value=mock_codes),
            patch.object(backup_crud, "mark_backup_code_as_used") as mock_mark_used,
        ):
            # Act
            result = backup_utils.verify_and_consume_backup_code(user_id, correct_code, verifier, mock_db)

            # Assert
            assert result is True
            # Every stored hash must have been verified (no early break).
            assert len(verify_calls) == len(mock_codes)
            # The first (matching) code is the one consumed.
            mock_mark_used.assert_called_once_with(mock_codes[0].id, user_id, mock_db)
