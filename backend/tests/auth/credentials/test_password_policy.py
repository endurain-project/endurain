"""Tests for the NIST SP 800-63B-4 password policy: length, blocklist, account details, NFC."""

import gzip
import hashlib
import json
import unicodedata
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import modules.auth.credentials.contracts as credentials_contracts
import modules.auth.credentials.password_hasher as credentials_password_hasher
import modules.auth.credentials.service as credentials_service

_DATA_DIR = Path(credentials_service.__file__).parent / "data"
_COMPOSED = "café-au-lait-noir"
_DECOMPOSED = "café-au-lait-noir"


def _settings(regular: int = 15, admin: int = 15) -> MagicMock:
    return MagicMock(password_length_regular_users=regular, password_length_admin_users=admin)


def _validate(
    password: str, *, access_type: str = "regular", username: str = "alice", email: str = "alice@example.com"
):
    return credentials_service.validate_and_hash_password_for_user(
        _settings(), access_type, password, username=username, email=email
    )


def _blocklist_entry() -> str:
    with gzip.open(_DATA_DIR / "password_blocklist.txt.gz", "rt", encoding="utf-8") as handle:
        return handle.readline().rstrip("\n")


class TestPolicyErrors:
    def test_codes_and_status(self):
        assert credentials_contracts.PasswordPolicyError.code == "password-rejected"
        for cls, code in (
            (credentials_contracts.PasswordTooShortError, "password-too-short"),
            (credentials_contracts.PasswordTooCommonError, "password-too-common"),
            (credentials_contracts.PasswordMatchesAccountError, "password-matches-account"),
        ):
            assert issubclass(cls, credentials_contracts.PasswordPolicyError)
            assert cls.code == code
            assert cls.status_code == 422


class TestLength:
    def test_too_short_names_minimum(self):
        with pytest.raises(credentials_contracts.PasswordTooShortError) as exc_info:
            _validate("short-pass")
        assert "15" in exc_info.value.detail

    def test_admin_minimum_is_used(self):
        settings = _settings(regular=8, admin=20)
        with pytest.raises(credentials_contracts.PasswordTooShortError) as exc_info:
            credentials_service.validate_and_hash_password_for_user(
                settings, "admin", "twelve-chars-ok-x", username="a", email="a@b.c"
            )
        assert "20" in exc_info.value.detail

    def test_length_counts_nfc_code_points(self):
        decomposed = "é" * 8  # 16 code points, 8 after NFC
        with pytest.raises(credentials_contracts.PasswordTooShortError):
            _validate(decomposed)

    def test_exactly_minimum_is_accepted(self):
        assert _validate("a1b2c3d4e5f6g7h").startswith("$")

    def test_no_composition_rules(self):
        assert _validate("onlylowercaseletters")


class TestBlocklist:
    def test_common_password_refused_case_insensitively(self):
        entry = _blocklist_entry()
        with pytest.raises(credentials_contracts.PasswordTooCommonError):
            credentials_service.validate_and_hash_password_for_user(
                _settings(8, 8), "regular", entry.upper(), username="alice", email="alice@example.com"
            )

    def test_blocklist_matches_nfc_equivalent(self):
        from modules.auth.credentials import password_policy

        entry = next(e for e in sorted(password_policy.load_blocklist()) if unicodedata.normalize("NFD", e) != e)
        decomposed = unicodedata.normalize("NFD", entry)
        assert decomposed != entry
        with pytest.raises(credentials_contracts.PasswordTooCommonError):
            credentials_service.validate_and_hash_password_for_user(
                _settings(8, 8), "regular", decomposed, username="alice", email="alice@example.com"
            )

    def test_blocklist_is_loaded_once(self):
        from modules.auth.credentials import password_policy

        assert password_policy.load_blocklist() is password_policy.load_blocklist()
        assert isinstance(password_policy.load_blocklist(), frozenset)


class TestAccountDetails:
    def test_email_local_part_is_refused(self):
        with pytest.raises(credentials_contracts.PasswordMatchesAccountError):
            credentials_service.validate_and_hash_password_for_user(
                _settings(8, 8), "regular", "Jane.Doe.Long", username="jd", email="jane.doe.long@example.com"
            )

    def test_full_email_is_refused(self):
        with pytest.raises(credentials_contracts.PasswordMatchesAccountError):
            credentials_service.validate_and_hash_password_for_user(
                _settings(8, 8),
                "regular",
                "Jane.Doe.Long@Example.com",
                username="jd",
                email="jane.doe.long@example.com",
            )

    def test_application_name_is_refused(self):
        with pytest.raises(credentials_contracts.PasswordMatchesAccountError):
            credentials_service.validate_and_hash_password_for_user(
                _settings(8, 8), "regular", "EnDuRain", username="jd", email="jd@example.com"
            )

    def test_username_is_refused_case_insensitively(self):
        with pytest.raises(credentials_contracts.PasswordMatchesAccountError):
            credentials_service.validate_and_hash_password_for_user(
                _settings(8, 8), "regular", "MyUserName", username="myusername", email="x@example.com"
            )

    def test_nfc_equivalent_username_is_refused(self):
        with pytest.raises(credentials_contracts.PasswordMatchesAccountError):
            credentials_service.validate_and_hash_password_for_user(
                _settings(8, 8), "regular", "josé-the-user", username="josé-the-user", email="x@example.com"
            )

    def test_substring_is_accepted(self):
        assert _validate("myusername-is-long-enough", username="myusername")


class TestHashForm:
    def test_stored_hash_is_of_the_nfc_form(self):
        hasher = credentials_password_hasher.get_password_hasher()
        stored = _validate(_DECOMPOSED)
        assert hasher.verify_password(_COMPOSED, stored)
        assert not hasher.verify_password(_DECOMPOSED, stored)


class TestVerifyAndUpdate:
    def test_decomposed_set_composed_typed(self):
        hasher = credentials_password_hasher.get_password_hasher()
        stored = _validate(_DECOMPOSED)
        ok, updated = credentials_service.verify_and_update_password(_COMPOSED, stored, hasher)
        assert ok and updated is None

    def test_composed_set_decomposed_typed(self):
        hasher = credentials_password_hasher.get_password_hasher()
        stored = _validate(_COMPOSED)
        ok, updated = credentials_service.verify_and_update_password(_DECOMPOSED, stored, hasher)
        assert ok and updated is None

    def test_legacy_raw_hash_verifies_and_migrates(self):
        hasher = credentials_password_hasher.get_password_hasher()
        legacy = hasher.hash_password(_DECOMPOSED)
        ok, updated = credentials_service.verify_and_update_password(_DECOMPOSED, legacy, hasher)
        assert ok
        assert updated is not None
        assert hasher.verify_password(_COMPOSED, updated)
        assert not hasher.verify_password(_DECOMPOSED, updated)

    def test_wrong_password_fails(self):
        hasher = credentials_password_hasher.get_password_hasher()
        stored = hasher.hash_password("right-password-here")
        assert credentials_service.verify_and_update_password("wrong-password-here", stored, hasher) == (False, None)
        assert credentials_service.verify_and_update_password(_DECOMPOSED, stored, hasher) == (False, None)

    def test_ascii_path_unchanged(self):
        hasher = credentials_password_hasher.get_password_hasher()
        stored = hasher.hash_password("plain-ascii-password")
        ok, updated = credentials_service.verify_and_update_password("plain-ascii-password", stored, hasher)
        assert ok and updated is None

    def test_ascii_password_calls_the_hasher_once(self):
        hasher = MagicMock()
        hasher.verify_and_update.return_value = (False, None)
        credentials_service.verify_and_update_password("ascii-password-1", "hash", hasher)
        assert hasher.verify_and_update.call_count == 1

    def test_generic_hasher_methods_do_not_normalise(self):
        hasher = credentials_password_hasher.get_password_hasher()
        stored = hasher.hash_password(_DECOMPOSED)
        assert hasher.verify_password(_DECOMPOSED, stored)
        assert not hasher.verify_password(_COMPOSED, stored)

    def test_hasher_has_no_composition_policy(self):
        assert not hasattr(credentials_password_hasher.PasswordHasher, "validate_password")
        assert not hasattr(credentials_password_hasher.PasswordHasher, "is_valid_password")


class TestBlocklistFile:
    def _manifest(self) -> dict:
        return json.loads((_DATA_DIR / "password_blocklist.json").read_text(encoding="utf-8"))

    def _lines(self) -> list[str]:
        with gzip.open(_DATA_DIR / "password_blocklist.txt.gz", "rt", encoding="utf-8") as handle:
            return handle.read().splitlines()

    def test_sha256_matches_manifest(self):
        digest = hashlib.sha256((_DATA_DIR / "password_blocklist.txt.gz").read_bytes()).hexdigest()
        assert digest == self._manifest()["sha256"]

    def test_entry_count_matches_manifest(self):
        assert len(self._lines()) == self._manifest()["entries"]

    def test_entries_are_sorted_and_unique(self):
        lines = self._lines()
        assert lines == sorted(lines)
        assert len(set(lines)) == len(lines)

    def test_entries_equal_their_runtime_compare_form(self):
        from modules.auth.credentials import password_policy

        for line in self._lines():
            assert password_policy.compare_form(line) == line
            assert 8 <= len(line) <= self._manifest()["max_entry_length"]

    def test_loaded_set_matches_file(self):
        from modules.auth.credentials import password_policy

        assert password_policy.load_blocklist() == frozenset(self._lines())
