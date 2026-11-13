"""Tests for auth.contracts module.

Covers all Principal helper methods, credential variant
construction, and the discriminated-union round-trip.
"""

import uuid
from datetime import UTC, datetime

import pytest

from modules.auth.contracts import (
    AccessTokenCred,
    AnyCredential,
    ApiKeyCred,
    OAuthCred,
    PasswordCred,
    Principal,
    SessionCookieCred,
)
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID

_SESSION_ID = uuid.UUID(int=7)
_KEY_ID = uuid.UUID(int=11)

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
        user_id=MOCK_USER_ID,
        username="testuser",
        email="test@example.com",
        is_active=True,
        is_superuser=False,
        scopes=frozenset({"account", "users:read"}),
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
        cred = AccessTokenCred(session_id=_SESSION_ID)
        assert cred.session_id == _SESSION_ID
        assert cred.jti is None
        assert cred.issued_at is None

    def test_access_token_cred_optional_fields(self):
        """AccessTokenCred stores optional jti and issued_at."""
        now = datetime.now(UTC)
        cred = AccessTokenCred(
            session_id=_SESSION_ID,
            jti="jti-abc",
            issued_at=now,
        )
        assert cred.jti == "jti-abc"
        assert cred.issued_at == now

    def test_api_key_cred_stores_id_and_prefix(self):
        """ApiKeyCred preserves api_key_id and key_prefix."""
        cred = ApiKeyCred(api_key_id=_KEY_ID, key_prefix="endurain")
        assert cred.api_key_id == _KEY_ID
        assert cred.key_prefix == "endurain"

    def test_session_cookie_cred_stores_session_id(self):
        """SessionCookieCred preserves session_id."""
        cred = SessionCookieCred(session_id=_SESSION_ID)
        assert cred.session_id == _SESSION_ID

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
        cred = AccessTokenCred(session_id=_SESSION_ID)
        p = Principal(
            user_id=OTHER_USER_ID,
            username="alice",
            email="alice@example.com",
            is_active=True,
            is_superuser=True,
            scopes=frozenset({"account"}),
            credential=cred,
        )
        assert p.user_id == OTHER_USER_ID
        assert p.username == "alice"
        assert p.email == "alice@example.com"
        assert p.is_active is True
        assert p.is_superuser is True
        assert "account" in p.scopes
        assert p.credential is cred

    def test_principal_is_frozen(self):
        """Principal is immutable after creation."""
        p = _make_principal(PasswordCred(username="alice"))
        with pytest.raises((AttributeError, TypeError)):
            p.user_id = uuid.uuid4()  # type: ignore[misc]

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
        cred = ApiKeyCred(api_key_id=_KEY_ID, key_prefix="abc")
        p = _make_principal(cred)
        assert p.is_api_key() is True

    def test_returns_false_for_access_token_cred(self):
        """is_api_key() returns False for AccessTokenCred."""
        p = _make_principal(AccessTokenCred(session_id=_SESSION_ID))
        assert p.is_api_key() is False

    def test_returns_false_for_password_cred(self):
        """is_api_key() returns False for PasswordCred."""
        p = _make_principal(PasswordCred(username="u"))
        assert p.is_api_key() is False

    def test_returns_false_for_session_cookie_cred(self):
        """is_api_key() returns False for SessionCookieCred."""
        p = _make_principal(SessionCookieCred(session_id=_SESSION_ID))
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
        p = _make_principal(AccessTokenCred(session_id=_SESSION_ID))
        assert p.credential_id() == str(_SESSION_ID)

    def test_session_cookie_cred_returns_session_id(self):
        """credential_id() returns session_id for SessionCookieCred."""
        p = _make_principal(SessionCookieCred(session_id=_SESSION_ID))
        assert p.credential_id() == str(_SESSION_ID)

    def test_api_key_cred_returns_the_key_id_as_text(self):
        """credential_id() returns api_key_id as text for ApiKeyCred."""
        p = _make_principal(ApiKeyCred(api_key_id=_KEY_ID, key_prefix="pre"))
        result = p.credential_id()
        assert result == str(_KEY_ID)
        assert isinstance(result, str)

    def test_oauth_cred_returns_composite_string(self):
        """credential_id() returns 'provider:external_id' for OAuthCred."""
        p = _make_principal(OAuthCred(provider="google", external_id="uid-001"))
        assert p.credential_id() == "google:uid-001"

    def test_password_cred_returns_none(self):
        """credential_id() returns None for PasswordCred."""
        p = _make_principal(PasswordCred(username="alice"))
        assert p.credential_id() is None


# ---------------------------------------------------------------------------
# credential_type helper
# ---------------------------------------------------------------------------


class TestCredentialType:
    """Tests for Principal.credential_type()."""

    @pytest.mark.parametrize(
        ("credential", "expected"),
        [
            (AccessTokenCred(session_id=_SESSION_ID), "access_token"),
            (SessionCookieCred(session_id=_SESSION_ID), "session_cookie"),
            (ApiKeyCred(api_key_id=_KEY_ID, key_prefix="pre"), "api_key"),
            (OAuthCred(provider="google", external_id="uid-001"), "oauth"),
            (PasswordCred(username="alice"), "password"),
        ],
    )
    def test_names_each_credential_variant(self, credential, expected):
        """credential_type() names how the principal authenticated."""
        assert _make_principal(credential).credential_type() == expected
