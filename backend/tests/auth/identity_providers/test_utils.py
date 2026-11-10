"""Tests for identity_providers.utils module."""

from types import SimpleNamespace
from typing import ClassVar

import pytest

import core.exceptions as core_exceptions
import modules.auth.identity_providers.utils as idp_utils
from modules.auth.computation import validate_pkce_challenge
from modules.auth.identity_providers.utils import (
    validate_redirect_url as _validate_redirect_url,
)

HOST = "https://app.example.com"


def validate_redirect_url(redirect, allowed_uris=None):
    return _validate_redirect_url(redirect, allowed_uris or set())


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

    def test_custom_scheme_allowed_when_listed(self):
        """A custom-scheme address in ALLOWED_REDIRECT_URIS must pass.

        Asserts:
            - No exception when the address is in the allowed set
        """
        validate_redirect_url("endurain://endurain/oauth/callback", {"endurain://endurain/oauth/callback"})

    def test_custom_scheme_case_insensitive(self):
        """The scheme comparison must be case-insensitive.

        Asserts:
            - ENDURAIN:// matches a listed endurain:// address
        """
        validate_redirect_url("ENDURAIN://endurain/callback", {"endurain://endurain/callback"})

    @pytest.mark.parametrize(
        "redirect", ["com.example.app:/oauth2redirect", "Com.Example.App:/oauth2redirect", "endurain:callback"]
    )
    def test_a_custom_scheme_without_an_authority_is_allowed_when_listed(self, redirect):
        """RFC 3986 ends the scheme at the first ':'; the '//' authority is optional (RFC 8252 7.1 callbacks)."""
        validate_redirect_url(redirect, {"com.example.app:/oauth2redirect", "endurain:callback"})

    def test_a_relative_path_with_a_colon_is_a_path(self):
        """A scheme starts with a letter, so a value starting with '/' never has one."""
        validate_redirect_url("/activities/a:b", set())

    # ------------------------------------------------------------------
    # Inputs that MUST raise HTTPException(400)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("redirect", ["HtTp://evil.example", "http://evil.example"])
    def test_http_scheme_in_any_case_is_rejected(self, redirect):
        """HTTP must be rejected regardless of letter case, even when listed.

        Asserts:
            - InvalidInputError with the external-redirect message
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url(redirect, {redirect})
        assert "External HTTP redirects are not allowed" in exc_info.value.detail

    @pytest.mark.parametrize("redirect", ["http:evil.example", "HTTP:evil.example/cb"])
    def test_http_scheme_without_slashes_is_rejected(self, redirect):
        """A browser reads "http:evil.example" as "http://evil.example/", so it is an external redirect too."""
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url(redirect, {"endurain://cb", "http:evil.example"})
        assert "External HTTP redirects are not allowed" in exc_info.value.detail

    @pytest.mark.parametrize(
        "redirect",
        [
            "https://evil.example",
            "HTTPS://evil.example",
            "HtTpS://evil.example/cb",
            "https:evil.example/cb",
            "https://",
        ],
    )
    def test_an_unlisted_https_redirect_is_rejected(self, redirect):
        """An https address is allowed only as an exact listed entry, in any letter case.

        Asserts:
            - InvalidInputError when the address is not listed, even if another https address is
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url(redirect, {"https://app.example.org/auth/sso/callback"})
        assert exc_info.value.status_code == 400

    @pytest.mark.parametrize(
        "redirect",
        [
            "https://app.example.org/auth/sso/callback/",
            "https://app.example.org/auth/sso/callback?x=1",
            "https://app.example.org:8443/auth/sso/callback",
            "https://evil.example/auth/sso/callback",
        ],
    )
    def test_a_near_miss_of_a_listed_https_address_is_rejected(self, redirect):
        with pytest.raises(core_exceptions.InvalidInputError):
            validate_redirect_url(redirect, {"https://app.example.org/auth/sso/callback"})

    @pytest.mark.parametrize(
        "redirect", ["https://app.example.org/auth/sso/callback", "HTTPS://app.example.org/auth/sso/callback"]
    )
    def test_a_listed_https_address_is_allowed(self, redirect):
        """An App Link / Universal Link address in ALLOWED_REDIRECT_URIS passes, the scheme in any letter case."""
        validate_redirect_url(redirect, {"https://app.example.org/auth/sso/callback"})

    @pytest.mark.parametrize(
        "redirect", ["JavaScript://x", "data://x", "file://x", "JavaScript:alert(1)", "data:text/html,x", "blob:x"]
    )
    def test_unsafe_scheme_is_rejected_even_when_allowed(self, redirect):
        """Unsafe schemes must be refused even when the address is listed.

        Asserts:
            - InvalidInputError when the address is in the allow-list
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url(redirect, {redirect})
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
        """A custom-scheme address with no ALLOWED_REDIRECT_URIS entry must be rejected.

        Asserts:
            - HTTPException 400 when no address is configured
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url("endurain://callback", set())
        assert exc_info.value.status_code == 400
        assert "not allowed" in exc_info.value.detail.lower()

    def test_wrong_custom_scheme_is_rejected(self):
        """An address not in the allow-list must be rejected even if others are.

        Asserts:
            - HTTPException 400 when only a different address is configured
        """
        with pytest.raises(core_exceptions.InvalidInputError) as exc_info:
            validate_redirect_url("myapp://callback", {"endurain://callback"})
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


class TestIsNativeRedirect:
    """Test suite for is_native_redirect."""

    def test_custom_scheme_is_true(self):
        """A custom URI scheme redirect is reported as custom.

        Asserts:
            - True for endurain://callback
        """
        assert idp_utils.is_native_redirect("endurain://callback") is True

    @pytest.mark.parametrize("redirect", ["https://app.example.org/auth/sso/callback", "HTTPS://app.example.org/cb"])
    def test_a_validated_https_address_is_true(self, redirect):
        """A listed claimed-https address is a native-app redirect, so it has already passed validation."""
        assert idp_utils.is_native_redirect(redirect) is True

    def test_custom_scheme_without_an_authority_is_true(self):
        """RFC 3986 ends the scheme at the first ':', so an RFC 8252 7.1 callback is a custom scheme."""
        assert idp_utils.is_native_redirect("com.example.app:/oauth2redirect") is True

    @pytest.mark.parametrize("redirect", ["/activities/a:b", "/x://y", "my app:/cb", "1app:/cb"])
    def test_a_value_without_a_well_formed_scheme_is_false(self, redirect):
        """A path or a malformed scheme name is not a custom-scheme redirect."""
        assert idp_utils.is_native_redirect(redirect) is False

    @pytest.mark.parametrize(
        "redirect", ["JavaScript://x", "data://x", "file://x", "javascript:alert(1)", "http:x", "HTTP://x"]
    )
    def test_unsafe_scheme_is_false(self, redirect):
        """Unsafe schemes are never treated as custom-scheme redirects.

        Asserts:
            - False for each unsafe scheme
        """
        assert idp_utils.is_native_redirect(redirect) is False


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

    def test_a_listed_https_address_is_not_host_prefixed(self):
        assert (
            idp_utils.build_link_result_url(HOST, "https://app.example.org/auth/sso/callback", "Google", success=True)
            == "https://app.example.org/auth/sso/callback?idp_link=success&idp_name=Google"
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


class TestValidateRedirectUrlWithExactAddresses:
    """Only the exact addresses in ALLOWED_REDIRECT_URIS are allowed; an empty set allows none."""

    URIS: ClassVar[set[str]] = {"endurain://oauth/callback", "gadgetbridge://auth"}

    def test_an_exact_address_is_allowed(self):
        validate_redirect_url("endurain://oauth/callback", self.URIS)
        validate_redirect_url("gadgetbridge://auth", self.URIS)

    def test_the_scheme_matches_in_any_letter_case(self):
        validate_redirect_url("ENDURAIN://oauth/callback", self.URIS)

    def test_the_rest_of_the_address_matches_exactly(self):
        validate_redirect_url("endurain://oauth/callback", self.URIS)
        with pytest.raises(core_exceptions.InvalidInputError, match="ALLOWED_REDIRECT_URIS"):
            validate_redirect_url("endurain://oauth/Callback", self.URIS)

    @pytest.mark.parametrize(
        "redirect",
        [
            "endurain://other",
            "endurain://oauth/callback/extra",
            "endurain://oauth/callback?x=1",
            "endurain://oauth/callback#frag",
        ],
    )
    def test_another_address_under_a_listed_scheme_is_refused(self, redirect):
        with pytest.raises(core_exceptions.InvalidInputError, match="ALLOWED_REDIRECT_URIS"):
            validate_redirect_url(redirect, self.URIS)

    def test_an_address_without_an_authority_matches_with_its_path_case_kept(self):
        uris = {"com.example.app:/Callback"}
        validate_redirect_url("com.example.app:/Callback", uris)
        validate_redirect_url("COM.Example.App:/Callback", uris)
        with pytest.raises(core_exceptions.InvalidInputError, match="ALLOWED_REDIRECT_URIS"):
            validate_redirect_url("com.example.app:/callback", uris)

    def test_relative_paths_stay_allowed(self):
        validate_redirect_url("/dashboard", self.URIS)

    def test_an_unsafe_scheme_is_refused_even_when_listed(self):
        with pytest.raises(core_exceptions.InvalidInputError):
            validate_redirect_url("javascript://x", {"javascript://x"})

    def test_without_addresses_a_custom_scheme_is_refused(self):
        with pytest.raises(core_exceptions.InvalidInputError, match="ALLOWED_REDIRECT_URIS"):
            validate_redirect_url("endurain://anything/at/all", set())
