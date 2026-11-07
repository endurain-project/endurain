"""Tests for the translation of identity-provider claims into local user fields."""

from unittest.mock import MagicMock

import pytest

import modules.auth.identity_providers.claim_mapping as claim_mapping


class TestMapUserClaims:
    """map_user_claims maps IdP claims to standard user fields."""

    def _idp(self, user_mapping=None) -> MagicMock:
        idp = MagicMock()
        idp.user_mapping = user_mapping
        return idp

    def test_default_mapping_prefers_preferred_username(self):
        claims = {
            "preferred_username": "alice",
            "email": "alice@example.com",
            "name": "Alice Example",
        }
        result = claim_mapping.map_user_claims(self._idp(), claims)
        assert result["username"] == "alice"
        assert result["email"] == "alice@example.com"
        assert result["name"] == "Alice Example"

    def test_name_loses_direction_controls_and_surrounding_space(self):
        result = claim_mapping.map_user_claims(self._idp(), {"name": " Eve\u202e evil\u2069 "})
        assert result["name"] == "Eve evil"

    def test_a_name_that_is_only_direction_controls_is_dropped(self):
        result = claim_mapping.map_user_claims(self._idp(), {"name": "\u202e \u200f", "sub": "s"})
        assert "name" not in result

    def test_name_keeps_zero_width_joiners(self):
        result = claim_mapping.map_user_claims(self._idp(), {"name": "ab\u200ccd"})
        assert result["name"] == "ab\u200ccd"

    def test_username_falls_back_through_claim_list(self):
        """With no preferred_username/username, it falls back to email then sub."""
        claims = {"email": "bob@example.com", "sub": "subject-123"}
        result = claim_mapping.map_user_claims(self._idp(), claims)
        assert result["username"] == "bob@example.com"

    def test_username_falls_back_to_sub_when_no_email(self):
        claims = {"sub": "subject-123"}
        result = claim_mapping.map_user_claims(self._idp(), claims)
        assert result["username"] == "subject-123"

    def test_custom_mapping_overrides_default(self):
        idp = self._idp(user_mapping={"username": ["custom_login"]})
        claims = {"custom_login": "custom-user", "preferred_username": "ignored"}
        result = claim_mapping.map_user_claims(idp, claims)
        assert result["username"] == "custom-user"

    def test_custom_mapping_accepts_string_value(self):
        """A custom mapping given as a bare string is treated as a single claim."""
        idp = self._idp(user_mapping={"username": "single_claim"})
        claims = {"single_claim": "value-x"}
        result = claim_mapping.map_user_claims(idp, claims)
        assert result["username"] == "value-x"

    def test_missing_claims_are_omitted(self):
        result = claim_mapping.map_user_claims(self._idp(), {})
        assert result == {}

    def test_empty_claim_values_are_skipped(self):
        """Falsy claim values are skipped so the next candidate wins."""
        claims = {"preferred_username": "", "username": "", "email": "real@example.com"}
        result = claim_mapping.map_user_claims(self._idp(), claims)
        assert result["username"] == "real@example.com"


class TestIsEmailVerified:
    """is_email_verified trusts email_verified only for an address taken from the standard email claim."""

    @staticmethod
    def _idp(user_mapping=None) -> MagicMock:
        idp = MagicMock()
        idp.user_mapping = user_mapping
        return idp

    @pytest.mark.parametrize(
        ("flag", "expected"),
        [
            (True, True),
            ("true", True),
            ("True", True),
            (" TRUE ", True),
            (False, False),
            ("false", False),
            ("1", False),
            (1, False),
            (None, False),
        ],
    )
    def test_email_claim_needs_a_true_flag(self, flag, expected):
        """Only an explicit boolean or 'true' assertion counts as verified."""
        claims = {"email": "a@example.com", "email_verified": flag}
        assert claim_mapping.is_email_verified(self._idp(), claims) is expected

    def test_missing_flag_is_unverified(self):
        assert claim_mapping.is_email_verified(self._idp(), {"email": "a@example.com"}) is False

    def test_mail_claim_is_never_verified(self):
        claims = {"mail": "a@example.com", "email_verified": True}
        assert claim_mapping.is_email_verified(self._idp(), claims) is False

    def test_email_claim_wins_over_mail(self):
        claims = {"email": "a@example.com", "mail": "b@example.com", "email_verified": True}
        assert claim_mapping.is_email_verified(self._idp(), claims) is True

    def test_custom_mapping_claim_is_never_verified(self):
        idp = self._idp(user_mapping={"email": ["work_email"]})
        claims = {"work_email": "a@example.com", "email": "other@example.com", "email_verified": True}
        assert claim_mapping.is_email_verified(idp, claims) is False

    def test_custom_mapping_to_the_email_claim_is_verified(self):
        idp = self._idp(user_mapping={"email": "email"})
        claims = {"email": "a@example.com", "email_verified": True}
        assert claim_mapping.is_email_verified(idp, claims) is True

    def test_no_email_is_unverified(self):
        assert claim_mapping.is_email_verified(self._idp(), {"email_verified": True}) is False
