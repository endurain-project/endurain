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
    """Unit tests for the is_email_verified claim parser."""

    @pytest.mark.parametrize(
        ("claims", "expected"),
        [
            ({"email_verified": True}, True),
            ({"email_verified": "true"}, True),
            ({"email_verified": "True"}, True),
            ({"email_verified": " TRUE "}, True),
            ({"email_verified": False}, False),
            ({"email_verified": "false"}, False),
            ({"email_verified": "1"}, False),
            ({"email_verified": 1}, False),
            ({"email_verified": None}, False),
            ({}, False),
        ],
    )
    def test_is_email_verified(self, claims, expected):
        """Only an explicit boolean/'true' assertion counts as verified."""
        assert claim_mapping.is_email_verified(claims) is expected
