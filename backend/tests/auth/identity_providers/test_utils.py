"""Tests for identity_providers.utils module."""

import pytest
from fastapi import HTTPException

from auth.identity_providers.utils import (
    validate_pkce_challenge,
    validate_pkce_verifier,
    _secure_compare,
    get_idp_template,
    get_idp_templates,
)
from auth.identity_providers.schema import IdentityProviderTemplate


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
        with pytest.raises(HTTPException) as exc_info:
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
        with pytest.raises(HTTPException) as exc_info:
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
        with pytest.raises(HTTPException) as exc_info:
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
        with pytest.raises(HTTPException) as exc_info:
            validate_pkce_challenge(code_challenge, code_challenge_method)

        assert exc_info.value.status_code == 400
        assert "valid base64url" in str(exc_info.value.detail)

    def test_validate_pkce_challenge_valid_base64url_characters(self):
        """Test PKCE challenge with all valid base64url characters.

        Asserts:
            - All base64url characters (A-Z, a-z, 0-9, -, _) are accepted
        """
        # Arrange
        code_challenge = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqr_-"  # 45 chars, valid
        )
        code_challenge_method = "S256"

        # Act & Assert (no exception should be raised)
        validate_pkce_challenge(code_challenge, code_challenge_method)


class TestValidatePkceVerifier:
    """Test suite for validate_pkce_verifier function."""

    def test_validate_pkce_verifier_success(self):
        """Test validating a valid PKCE verifier.

        Asserts:
            - Valid verifier that matches challenge passes validation
        """
        # Arrange
        # Valid verifier (RFC 7636 compliant)
        code_verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        # Corresponding S256 challenge
        code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        code_challenge_method = "S256"

        # Act & Assert (no exception should be raised)
        validate_pkce_verifier(code_verifier, code_challenge, code_challenge_method)

    def test_validate_pkce_verifier_min_length_violation(self):
        """Test PKCE verifier minimum length validation.

        Asserts:
            - HTTPException is raised for verifier shorter than 43 chars
        """
        # Arrange
        code_verifier = "a" * 42  # Too short
        code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        code_challenge_method = "S256"

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            validate_pkce_verifier(code_verifier, code_challenge, code_challenge_method)

        assert exc_info.value.status_code == 400
        assert "43-128 characters" in str(exc_info.value.detail)

    def test_validate_pkce_verifier_max_length_violation(self):
        """Test PKCE verifier maximum length validation.

        Asserts:
            - HTTPException is raised for verifier longer than 128 chars
        """
        # Arrange
        code_verifier = "a" * 129  # Too long
        code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        code_challenge_method = "S256"

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            validate_pkce_verifier(code_verifier, code_challenge, code_challenge_method)

        assert exc_info.value.status_code == 400
        assert "43-128 characters" in str(exc_info.value.detail)

    def test_validate_pkce_verifier_invalid_characters(self):
        """Test PKCE verifier with invalid characters.

        Asserts:
            - HTTPException is raised for non-base64url characters
        """
        # Arrange
        code_verifier = "a" * 43 + "!@#"  # Invalid characters
        code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        code_challenge_method = "S256"

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            validate_pkce_verifier(code_verifier, code_challenge, code_challenge_method)

        assert exc_info.value.status_code == 400
        assert "valid base64url" in str(exc_info.value.detail)

    def test_validate_pkce_verifier_wrong_method(self):
        """Test PKCE verifier with wrong challenge method.

        Asserts:
            - HTTPException is raised for non-S256 method
        """
        # Arrange
        code_verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        code_challenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        code_challenge_method = "plain"

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            validate_pkce_verifier(code_verifier, code_challenge, code_challenge_method)

        assert exc_info.value.status_code == 400
        assert "Only S256 PKCE method is supported" in str(exc_info.value.detail)

    def test_validate_pkce_verifier_mismatch(self):
        """Test PKCE verifier that doesn't match challenge.

        Asserts:
            - HTTPException is raised for mismatched verifier
        """
        # Arrange
        code_verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        code_challenge = "wrong_challenge_value_that_does_not_match_verifier"
        code_challenge_method = "S256"

        # Act & Assert
        with pytest.raises(HTTPException) as exc_info:
            validate_pkce_verifier(code_verifier, code_challenge, code_challenge_method)

        assert exc_info.value.status_code == 400
        assert "Invalid code_verifier" in str(exc_info.value.detail)


class TestSecureCompare:
    """Test suite for _secure_compare function."""

    def test_secure_compare_equal_strings(self):
        """Test secure comparison of equal strings.

        Asserts:
            - Returns True for identical strings
        """
        # Arrange
        str1 = "test_string_123"
        str2 = "test_string_123"

        # Act
        result = _secure_compare(str1, str2)

        # Assert
        assert result is True

    def test_secure_compare_different_strings(self):
        """Test secure comparison of different strings.

        Asserts:
            - Returns False for different strings
        """
        # Arrange
        str1 = "test_string_123"
        str2 = "test_string_456"

        # Act
        result = _secure_compare(str1, str2)

        # Assert
        assert result is False

    def test_secure_compare_different_lengths(self):
        """Test secure comparison of strings with different lengths.

        Asserts:
            - Returns False for strings of different lengths
        """
        # Arrange
        str1 = "short"
        str2 = "much_longer_string"

        # Act
        result = _secure_compare(str1, str2)

        # Assert
        assert result is False

    def test_secure_compare_empty_strings(self):
        """Test secure comparison of empty strings.

        Asserts:
            - Returns True for both empty strings
        """
        # Arrange
        str1 = ""
        str2 = ""

        # Act
        result = _secure_compare(str1, str2)

        # Assert
        assert result is True

    def test_secure_compare_one_empty_string(self):
        """Test secure comparison with one empty string.

        Asserts:
            - Returns False when one string is empty
        """
        # Arrange
        str1 = "non_empty"
        str2 = ""

        # Act
        result = _secure_compare(str1, str2)

        # Assert
        assert result is False

    def test_secure_compare_case_sensitive(self):
        """Test secure comparison is case-sensitive.

        Asserts:
            - Returns False for strings differing only in case
        """
        # Arrange
        str1 = "TestString"
        str2 = "teststring"

        # Act
        result = _secure_compare(str1, str2)

        # Assert
        assert result is False


class TestGetIdpTemplate:
    """Test suite for get_idp_template function."""

    def test_get_idp_template_keycloak(self):
        """Test retrieving Keycloak IdP template.

        Asserts:
            - Keycloak template is returned with correct structure
        """
        # Act
        template = get_idp_template("keycloak")

        # Assert
        assert template is not None
        assert template["name"] == "Keycloak"
        assert template["provider_type"] == "oidc"
        assert "issuer_url" in template
        assert "scopes" in template
        assert "user_mapping" in template

    def test_get_idp_template_authentik(self):
        """Test retrieving Authentik IdP template.

        Asserts:
            - Authentik template is returned with correct structure
        """
        # Act
        template = get_idp_template("authentik")

        # Assert
        assert template is not None
        assert template["name"] == "Authentik"
        assert template["provider_type"] == "oidc"

    def test_get_idp_template_authelia(self):
        """Test retrieving Authelia IdP template.

        Asserts:
            - Authelia template is returned with correct structure
        """
        # Act
        template = get_idp_template("authelia")

        # Assert
        assert template is not None
        assert template["name"] == "Authelia"
        assert template["provider_type"] == "oidc"

    def test_get_idp_template_casdoor(self):
        """Test retrieving Casdoor IdP template.

        Asserts:
            - Casdoor template is returned with correct structure
        """
        # Act
        template = get_idp_template("casdoor")

        # Assert
        assert template is not None
        assert template["name"] == "Casdoor"
        assert template["provider_type"] == "oidc"

    def test_get_idp_template_pocketid(self):
        """Test retrieving Pocket ID template.

        Asserts:
            - Pocket ID template is returned with correct structure
        """
        # Act
        template = get_idp_template("pocketid")

        # Assert
        assert template is not None
        assert template["name"] == "Pocket ID"
        assert template["provider_type"] == "oidc"

    def test_get_idp_template_nonexistent(self):
        """Test retrieving non-existent IdP template.

        Asserts:
            - None is returned for non-existent template
        """
        # Act
        template = get_idp_template("nonexistent_provider")

        # Assert
        assert template is None


class TestGetIdpTemplates:
    """Test suite for get_idp_templates function."""

    def test_get_idp_templates_returns_list(self):
        """Test get_idp_templates returns a list.

        Asserts:
            - Returns a list of IdentityProviderTemplate objects
        """
        # Act
        templates = get_idp_templates()

        # Assert
        assert isinstance(templates, list)
        assert len(templates) > 0
        assert all(isinstance(t, IdentityProviderTemplate) for t in templates)

    def test_get_idp_templates_contains_expected_providers(self):
        """Test get_idp_templates contains expected providers.

        Asserts:
            - List contains Keycloak, Authentik, Authelia, Casdoor, Pocket ID
        """
        # Act
        templates = get_idp_templates()

        # Assert
        template_ids = [t.template_id for t in templates]
        assert "keycloak" in template_ids
        assert "authentik" in template_ids
        assert "authelia" in template_ids
        assert "casdoor" in template_ids
        assert "pocketid" in template_ids

    def test_get_idp_templates_structure(self):
        """Test each template has required structure.

        Asserts:
            - Each template has required fields
        """
        # Act
        templates = get_idp_templates()

        # Assert
        for template in templates:
            assert hasattr(template, "template_id")
            assert hasattr(template, "name")
            assert hasattr(template, "provider_type")
            assert hasattr(template, "scopes")
            assert hasattr(template, "description")

    def test_get_idp_templates_all_oidc(self):
        """Test all templates are OIDC providers.

        Asserts:
            - All templates have provider_type 'oidc'
        """
        # Act
        templates = get_idp_templates()

        # Assert
        for template in templates:
            assert template.provider_type == "oidc"

    def test_get_idp_templates_has_user_mapping(self):
        """Test templates include user mapping configuration.

        Asserts:
            - Each template has user_mapping with username and email
        """
        # Act
        templates = get_idp_templates()

        # Assert
        for template in templates:
            assert template.user_mapping is not None
            assert "username" in template.user_mapping
            assert "email" in template.user_mapping
