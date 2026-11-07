"""Tests for identity_providers.utils module."""

from types import SimpleNamespace

import pytest

import core.exceptions as core_exceptions
import modules.auth.identity_providers.utils as idp_utils
from modules.auth.computation import validate_pkce_challenge
from modules.auth.identity_providers.utils import (
    validate_redirect_url as _validate_redirect_url,
)

HOST = "https://app.example.com"


def validate_redirect_url(redirect, allowed_schemes=None):
    if allowed_schemes is None:
        allowed_schemes = {"endurain"}
    return _validate_redirect_url(redirect, allowed_schemes)


class TestValidatePkceChallenge:
    """Test suite for validate_pkce_challenge function."""

    def test_validate_pkce_challenge_success(self):
        """Test validating a valid PKCE challenge.

        Asserts:
            - Valid S256 challenge passes validation
        """
        # Arrange
        # Valid base64url-encoded SHA256 hash (43 chars minimum)
        code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        code_challenge_method = "S256"

        # Act & Assert (no exception should be raised)
        validate_pkce_challenge(code_challenge, code_challenge_method)

    def test_validate_pkce_challenge_plain_method_rejected(self):
        """Test PKCE plain method is rejected.

        Asserts:
            - HTTPException with 400 status is raised for 'plain' method
        """
        # Arrange
        code_challenge = "test_challenge"
        code_challenge_method = "plain"

        # Act & Assert
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_pkce_challenge(code_challenge, code_challenge_method)

        assert exc_info.value.status_code == 400
        assert "Only S256 PKCE method is supported" in str(exc_info.value.detail)

    def test_validate_pkce_challenge_min_length_violation(self):
        """Test PKCE challenge minimum length validation.

        Asserts:
            - HTTPException is raised for challenge shorter than 43 chars
        """
        # Arrange
        code_challenge = "a" * 42  # Too short
        code_challenge_method = "S256"

        # Act & Assert
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_pkce_challenge(code_challenge, code_challenge_method)

        assert exc_info.value.status_code == 400
        assert "43-128 characters" in str(exc_info.value.detail)

    def test_validate_pkce_challenge_max_length_violation(self):
        """Test PKCE challenge maximum length validation.

        Asserts:
            - HTTPException is raised for challenge longer than 128 chars
        """
        # Arrange
        code_challenge = "a" * 129  # Too long
        code_challenge_method = "S256"

        # Act & Assert
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_pkce_challenge(code_challenge, code_challenge_method)

        assert exc_info.value.status_code == 400
        assert "43-128 characters" in str(exc_info.value.detail)

    def test_validate_pkce_challenge_invalid_characters(self):
        """Test PKCE challenge with invalid characters.

        Asserts:
            - HTTPException is raised for non-base64url characters
        """
        # Arrange
        code_challenge = "a" * 43 + "!@#$"  # Invalid characters
        code_challenge_method = "S256"

        # Act & Assert
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_pkce_challenge(code_challenge, code_challenge_method)

        assert exc_info.value.status_code == 400
        assert "valid base64url" in str(exc_info.value.detail)

    def test_validate_pkce_challenge_valid_base64url_characters(self):
        """Test PKCE challenge with all valid base64url characters.

        Asserts:
            - All base64url characters (A-Z, a-z, 0-9, -, _) are accepted
        """
        # Arrange
        code_challenge = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqr_-"  # 45 chars, valid
        code_challenge_method = "S256"

        # Act & Assert (no exception should be raised)
        validate_pkce_challenge(code_challenge, code_challenge_method)


class TestValidateRedirectUrl:
    """Test suite for validate_redirect_url function.

    Validates the open-redirect prevention logic. Only relative paths
    and explicitly allowed custom URI schemes must be accepted.
    """

    # ------------------------------------------------------------------
    # Safe inputs that must NOT raise
    # ------------------------------------------------------------------

    def test_none_is_allowed(self):
        """None (optional redirect) must pass silently.

        Asserts:
            - No exception raised for None input
        """
        validate_redirect_url(None)

    def test_empty_string_is_allowed(self):
        """Empty string must pass silently.

        Asserts:
            - No exception raised for empty string
        """
        validate_redirect_url("")

    def test_whitespace_only_is_allowed(self):
        """Whitespace-only string must pass silently.

        Asserts:
            - No exception raised for whitespace-only input
        """
        validate_redirect_url("   ")

    def test_relative_path_root_is_allowed(self):
        """Root relative path '/' must be allowed.

        Asserts:
            - No exception raised for '/'
        """
        validate_redirect_url("/")

    def test_relative_path_dashboard_is_allowed(self):
        """Typical relative path must be allowed.

        Asserts:
            - No exception raised for '/dashboard'
        """
        validate_redirect_url("/dashboard")

    def test_relative_path_with_query_string_is_allowed(self):
        """Relative path with query string must be allowed.

        Asserts:
            - No exception raised for '/settings?tab=security'
        """
        validate_redirect_url("/settings?tab=security")

    def test_custom_scheme_allowed_when_configured(self):
        """Custom URI scheme in ALLOWED_REDIRECT_SCHEMES must pass.

        Asserts:
            - No exception when scheme is in allowed set
        """
        validate_redirect_url("endurain://endurain/oauth/callback", {"endurain"})

    def test_custom_scheme_case_insensitive(self):
        """Scheme comparison must be case-insensitive.

        Asserts:
            - ENDURAIN:// is allowed when 'endurain' configured
        """
        validate_redirect_url("ENDURAIN://endurain/callback", {"endurain"})

    def test_multiple_custom_schemes_allowed(self):
        """Multiple schemes can be configured simultaneously.

        Asserts:
            - Both schemes accepted independently
        """
        schemes = {"endurain", "myapp"}
        validate_redirect_url("endurain://callback", schemes)
        validate_redirect_url("myapp://callback", schemes)

    def test_mixed_case_custom_scheme_allowed_when_configured(self):
        """A mixed-case custom scheme must match its lower-case allow-list entry.

        Asserts:
            - Endurain://callback is accepted when 'endurain' is configured
        """
        validate_redirect_url("Endurain://callback", {"endurain"})

    # ------------------------------------------------------------------
    # Inputs that MUST raise HTTPException(400)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("redirect", ["HTTPS://evil.example", "HtTp://evil.example"])
    def test_external_http_scheme_in_any_case_is_rejected(self, redirect):
        """External HTTP/HTTPS URLs must be rejected regardless of letter case.

        Asserts:
            - InvalidInputError with the external-redirect message
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url(redirect)
        assert "External HTTP redirects are not allowed" in exc_info.value.detail

    @pytest.mark.parametrize("redirect", ["JavaScript://x", "data://x", "file://x"])
    def test_unsafe_scheme_is_rejected_even_when_allowed(self, redirect):
        """Unsafe schemes must be refused even when listed in allowed_schemes.

        Asserts:
            - InvalidInputError when the scheme is in the allow-list
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url(redirect, {"endurain", "javascript", "data", "file"})
        assert exc_info.value.status_code == 400

    def test_http_url_is_rejected(self):
        """External http:// URL must be rejected.

        Asserts:
            - HTTPException 400 for http://evil.com
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url("http://evil.com")
        assert exc_info.value.status_code == 400

    def test_https_url_is_rejected(self):
        """External https:// URL must be rejected.

        Asserts:
            - HTTPException 400 for https://evil.com
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url("https://evil.com")
        assert exc_info.value.status_code == 400

    def test_https_localhost_is_rejected(self):
        """Localhost https URL must also be rejected.

        Asserts:
            - HTTPException 400 for https://localhost:8080
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url("https://localhost:8080")
        assert exc_info.value.status_code == 400

    def test_custom_scheme_not_in_allowlist_is_rejected(self):
        """Custom scheme not in ALLOWED_REDIRECT_SCHEMES must be rejected.

        Asserts:
            - HTTPException 400 when scheme not configured
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url("endurain://callback", set())
        assert exc_info.value.status_code == 400
        assert "not allowed" in exc_info.value.detail.lower()

    def test_wrong_custom_scheme_is_rejected(self):
        """Scheme not in the allow-list must be rejected even if others are.

        Asserts:
            - HTTPException 400 when only a different scheme is configured
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url("myapp://callback", {"endurain"})
        assert exc_info.value.status_code == 400

    def test_path_traversal_double_dot_is_rejected(self):
        """Path traversal via '..' must be rejected.

        Asserts:
            - HTTPException 400 for /../etc/passwd
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url("/../etc/passwd")
        assert exc_info.value.status_code == 400

    def test_path_traversal_double_dot_mid_path_is_rejected(self):
        """Path traversal via '..' in middle of path must be rejected.

        Asserts:
            - HTTPException 400 for /valid/../etc/passwd
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url("/valid/../etc/passwd")
        assert exc_info.value.status_code == 400

    def test_path_traversal_backslash_is_rejected(self):
        """Backslash in path (Windows-style traversal) must be rejected.

        Asserts:
            - HTTPException 400 for /path\\to\\file
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url("/path\\to\\file")
        assert exc_info.value.status_code == 400

    @pytest.mark.parametrize(
        "redirect",
        ["/\t/evil.com", "/\n/evil.com", "/\r/evil.com", "/ok\x00", "/ok\x7f", "/a\tb", "\t/dashboard", "/dashboard\n"],
    )
    def test_control_characters_are_rejected(self, redirect):
        """A browser drops tab, CR and LF inside a URL, so "/<tab>/host" becomes "//host".

        Asserts:
            - HTTPException 400 for control characters anywhere in the value, including
              leading and trailing ones that ``strip()`` would otherwise hide
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url(redirect)
        assert exc_info.value.status_code == 400

    def test_double_slash_protocol_relative_is_rejected(self):
        """Protocol-relative URLs (//) must be rejected.

        Asserts:
            - HTTPException 400 for //evil.com
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url("//evil.com")
        assert exc_info.value.status_code == 400

    def test_no_leading_slash_relative_path_is_rejected(self):
        """Relative path not starting with '/' must be rejected.

        Asserts:
            - HTTPException 400 for 'dashboard' (no leading slash)
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url("dashboard")
        assert exc_info.value.status_code == 400

    def test_javascript_scheme_is_rejected(self):
        """javascript: URI scheme must be rejected (XSS vector).

        Asserts:
            - HTTPException 400 for javascript:alert(1)
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url("javascript:alert(1)")
        assert exc_info.value.status_code == 400


class TestIsCustomSchemeRedirect:
    """Test suite for is_custom_scheme_redirect."""

    def test_custom_scheme_is_true(self):
        """A custom URI scheme redirect is reported as custom.

        Asserts:
            - True for endurain://callback
        """
        assert idp_utils.is_custom_scheme_redirect("endurain://callback") is True

    def test_https_in_any_case_is_false(self):
        """External HTTPS redirects are never custom-scheme redirects.

        Asserts:
            - False for HTTPS://x
        """
        assert idp_utils.is_custom_scheme_redirect("HTTPS://x") is False

    @pytest.mark.parametrize("redirect", ["JavaScript://x", "data://x", "file://x"])
    def test_unsafe_scheme_is_false(self, redirect):
        """Unsafe schemes are never treated as custom-scheme redirects.

        Asserts:
            - False for each unsafe scheme
        """
        assert idp_utils.is_custom_scheme_redirect(redirect) is False


class TestAppendQueryParams:
    def test_appends_to_path_without_query(self):
        assert idp_utils.append_query_params("/settings/security", {"idp_link": "success"}) == (
            "/settings/security?idp_link=success"
        )

    def test_preserves_existing_query(self):
        assert idp_utils.append_query_params("/settings?tab=security", {"idp_link": "success"}) == (
            "/settings?tab=security&idp_link=success"
        )

    def test_url_encodes_values(self):
        assert idp_utils.append_query_params("/settings/security", {"idp_name": "My IdP"}) == (
            "/settings/security?idp_name=My+IdP"
        )


class TestBuildLinkResultUrl:
    def test_default_path_when_no_return_path(self):
        assert idp_utils.build_link_result_url(HOST, None, "Google", success=True) == (
            f"{HOST}/settings/security?idp_link=success&idp_name=Google"
        )

    def test_honors_relative_return_path(self):
        assert idp_utils.build_link_result_url(HOST, "/settings/security", "Google", success=True) == (
            f"{HOST}/settings/security?idp_link=success&idp_name=Google"
        )

    def test_custom_scheme_is_not_host_prefixed(self):
        assert idp_utils.build_link_result_url(HOST, "gadgetbridge://callback", "Google", success=True) == (
            "gadgetbridge://callback?idp_link=success&idp_name=Google"
        )

    def test_error_omits_idp_name(self):
        assert idp_utils.build_link_result_url(HOST, "/settings/security", None, success=False) == (
            f"{HOST}/settings/security?idp_link=error"
        )

    def test_error_falls_back_to_default_path(self):
        assert idp_utils.build_link_result_url(HOST, None, None, success=False) == (
            f"{HOST}/settings/security?idp_link=error"
        )


class TestBuildRedirectUri:
    """build_redirect_uri builds the public callback URL."""

    def test_builds_expected_callback_url(self):
        uri = idp_utils.build_redirect_uri("https://endurain.example", "my-idp")
        assert uri == "https://endurain.example/api/v1/public/idp/callback/my-idp"


class TestRequiresIdToken:
    """A sign-in must carry a verified ID token when the provider will issue one."""

    @pytest.mark.parametrize(
        ("provider_type", "scopes", "expected"),
        [
            ("oidc", "openid profile email", True),
            ("oidc", "profile email", True),
            ("oauth2", "openid profile email", True),
            ("oauth2", "profile openid", True),
            ("oauth2", None, True),
            ("oauth2", "", True),
            ("oauth2", "read:user user:email", False),
            ("oauth2", "openid2 profile", False),
        ],
    )
    def test_oidc_always_and_oauth2_only_with_the_openid_scope(self, provider_type, scopes, expected):
        idp = SimpleNamespace(provider_type=provider_type, scopes=scopes)

        assert idp_utils.requires_id_token(idp) is expected


class TestNormalizeIssuerUrl:
    """The normalized issuer drops every trailing slash, as the SQL ``rtrim(issuer_url, '/')`` does."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("https://a.example.com", "https://a.example.com"),
            ("https://a.example.com/", "https://a.example.com"),
            ("https://a.example.com//", "https://a.example.com"),
            ("https://a.example.com/realm/", "https://a.example.com/realm"),
        ],
    )
    def test_removes_every_trailing_slash(self, value, expected):
        assert idp_utils.normalize_issuer_url(value) == expected
