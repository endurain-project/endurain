"""Tests for auth.principal module.

Covers all Principal helper methods, credential variant
construction, and the discriminated-union round-trip.
"""

from datetime import UTC, datetime

import pytest

from modules.auth.principal import (
    AccessTokenCred,
    AnyCredential,
    ApiKeyCred,
    OAuthCred,
    PasswordCred,
    Principal,
    SessionCookieCred,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_principal(credential: AnyCredential) -> Principal:
    """Build a minimal valid Principal with the given credential.

    Args:
        credential: Credential variant to attach.

    Returns:
        Principal: Fully populated, frozen principal.
    """
    return Principal(
        user_id=1,
        username="testuser",
        email="test@example.com",
        is_active=True,
        is_superuser=False,
        scopes=frozenset({"profile", "users:read"}),
        credential=credential,
    )


# ---------------------------------------------------------------------------
# Credential variant construction
# ---------------------------------------------------------------------------


class TestCredentialVariants:
    """Round-trip tests for each credential variant."""

    def test_password_cred_stores_username(self):
        """PasswordCred preserves the username field."""
        cred = PasswordCred(username="alice")
        assert cred.username == "alice"

    def test_access_token_cred_required_field(self):
        """AccessTokenCred requires session_id."""
        cred = AccessTokenCred(session_id="sid-123")
        assert cred.session_id == "sid-123"
        assert cred.jti is None
        assert cred.issued_at is None

    def test_access_token_cred_optional_fields(self):
        """AccessTokenCred stores optional jti and issued_at."""
        now = datetime.now(UTC)
        cred = AccessTokenCred(
            session_id="sid-456",
            jti="jti-abc",
            issued_at=now,
        )
        assert cred.jti == "jti-abc"
        assert cred.issued_at == now

    def test_api_key_cred_stores_id_and_prefix(self):
        """ApiKeyCred preserves api_key_id and key_prefix."""
        cred = ApiKeyCred(api_key_id=42, key_prefix="endurain")
        assert cred.api_key_id == 42
        assert cred.key_prefix == "endurain"

    def test_session_cookie_cred_stores_session_id(self):
        """SessionCookieCred preserves session_id."""
        cred = SessionCookieCred(session_id="sess-789")
        assert cred.session_id == "sess-789"

    def test_oauth_cred_stores_provider_and_external_id(self):
        """OAuthCred preserves provider and external_id."""
        cred = OAuthCred(provider="google", external_id="uid-001")
        assert cred.provider == "google"
        assert cred.external_id == "uid-001"

    def test_credentials_are_frozen(self):
        """Credential dataclasses are immutable."""
        cred = PasswordCred(username="alice")
        with pytest.raises((AttributeError, TypeError)):
            cred.username = "bob"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Principal construction
# ---------------------------------------------------------------------------


class TestPrincipalConstruction:
    """Tests for Principal field storage and immutability."""

    def test_fields_are_stored(self):
        """All Principal fields are stored correctly."""
        cred = AccessTokenCred(session_id="sid-1")
        p = Principal(
            user_id=7,
            username="alice",
            email="alice@example.com",
            is_active=True,
            is_superuser=True,
            scopes=frozenset({"profile"}),
            credential=cred,
        )
        assert p.user_id == 7
        assert p.username == "alice"
        assert p.email == "alice@example.com"
        assert p.is_active is True
        assert p.is_superuser is True
        assert "profile" in p.scopes
        assert p.credential is cred

    def test_principal_is_frozen(self):
        """Principal is immutable after creation."""
        p = _make_principal(PasswordCred(username="alice"))
        with pytest.raises((AttributeError, TypeError)):
            p.user_id = 999  # type: ignore[misc]

    def test_scopes_is_frozenset(self):
        """Principal.scopes is a frozenset."""
        p = _make_principal(PasswordCred(username="alice"))
        assert isinstance(p.scopes, frozenset)


# ---------------------------------------------------------------------------
# is_api_key helper
# ---------------------------------------------------------------------------


class TestIsApiKey:
    """Tests for Principal.is_api_key()."""

    def test_returns_true_for_api_key_cred(self):
        """is_api_key() returns True when credential is ApiKeyCred."""
        cred = ApiKeyCred(api_key_id=1, key_prefix="abc")
        p = _make_principal(cred)
        assert p.is_api_key() is True

    def test_returns_false_for_access_token_cred(self):
        """is_api_key() returns False for AccessTokenCred."""
        p = _make_principal(AccessTokenCred(session_id="s"))
        assert p.is_api_key() is False

    def test_returns_false_for_password_cred(self):
        """is_api_key() returns False for PasswordCred."""
        p = _make_principal(PasswordCred(username="u"))
        assert p.is_api_key() is False

    def test_returns_false_for_session_cookie_cred(self):
        """is_api_key() returns False for SessionCookieCred."""
        p = _make_principal(SessionCookieCred(session_id="s"))
        assert p.is_api_key() is False

    def test_returns_false_for_oauth_cred(self):
        """is_api_key() returns False for OAuthCred."""
        p = _make_principal(OAuthCred(provider="github", external_id="x"))
        assert p.is_api_key() is False


# ---------------------------------------------------------------------------
# credential_id helper
# ---------------------------------------------------------------------------


class TestCredentialId:
    """Tests for Principal.credential_id()."""

    def test_access_token_cred_returns_session_id(self):
        """credential_id() returns session_id for AccessTokenCred."""
        p = _make_principal(AccessTokenCred(session_id="sid-abc"))
        assert p.credential_id() == "sid-abc"

    def test_session_cookie_cred_returns_session_id(self):
        """credential_id() returns session_id for SessionCookieCred."""
        p = _make_principal(SessionCookieCred(session_id="sess-xyz"))
        assert p.credential_id() == "sess-xyz"

    def test_api_key_cred_returns_integer_id(self):
        """credential_id() returns api_key_id (int) for ApiKeyCred."""
        p = _make_principal(ApiKeyCred(api_key_id=99, key_prefix="pre"))
        result = p.credential_id()
        assert result == 99
        assert isinstance(result, int)

    def test_oauth_cred_returns_composite_string(self):
        """credential_id() returns 'provider:external_id' for OAuthCred."""
        p = _make_principal(OAuthCred(provider="google", external_id="uid-001"))
        assert p.credential_id() == "google:uid-001"

    def test_password_cred_returns_none(self):
        """credential_id() returns None for PasswordCred."""
        p = _make_principal(PasswordCred(username="alice"))
        assert p.credential_id() is None
