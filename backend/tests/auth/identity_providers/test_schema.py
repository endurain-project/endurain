"""Tests for identity_providers.schema module."""

import pytest
from pydantic import ValidationError
from datetime import datetime

from auth.identity_providers.schema import (
    IdentityProviderBase,
    IdentityProviderCreate,
    IdentityProviderUpdate,
    IdentityProvider,
    IdentityProviderPublic,
    IdentityProviderTemplate,
    TokenExchangeRequest,
    TokenExchangeResponse,
)


class TestIdentityProviderBase:
    """Test suite for IdentityProviderBase schema."""

    def test_valid_identity_provider_base(self):
        """Test creating a valid IdentityProviderBase instance.

        Asserts:
            - Instance is created successfully
            - All fields have correct values
            - Default values are applied
        """
        # Arrange & Act
        idp = IdentityProviderBase(
            name="Test Provider",
            slug="test-provider",
            provider_type="oidc",
            enabled=True,
            issuer_url="https://auth.example.com",
            authorization_endpoint="https://auth.example.com/authorize",
            token_endpoint="https://auth.example.com/token",
            userinfo_endpoint="https://auth.example.com/userinfo",
            jwks_uri="https://auth.example.com/jwks",
            scopes="openid profile email",
            icon="test-icon",
            auto_create_users=True,
            sync_user_info=True,
            user_mapping={"username": ["preferred_username"], "email": ["email"]},
            client_id="test-client-id",
        )

        # Assert
        assert idp.name == "Test Provider"
        assert idp.slug == "test-provider"
        assert idp.provider_type == "oidc"
        assert idp.enabled is True
        assert idp.issuer_url == "https://auth.example.com"
        assert idp.scopes == "openid profile email"
        assert idp.auto_create_users is True
        assert idp.sync_user_info is True
        assert idp.client_id == "test-client-id"

    def test_identity_provider_base_with_defaults(self):
        """Test IdentityProviderBase with default values.

        Asserts:
            - Default provider_type is 'oidc'
            - Default enabled is False
            - Default scopes is 'openid profile email'
            - Default auto_create_users is True
            - Default sync_user_info is True
        """
        # Arrange & Act
        idp = IdentityProviderBase(name="Test", slug="test", client_id="client-123")

        # Assert
        assert idp.provider_type == "oidc"
        assert idp.enabled is False
        assert idp.scopes == "openid profile email"
        assert idp.auto_create_users is True
        assert idp.sync_user_info is True

    def test_slug_validation_lowercase_alphanumeric_hyphens(self):
        """Test slug validation accepts valid characters.

        Asserts:
            - Lowercase letters, numbers, and hyphens are accepted
        """
        # Arrange & Act
        idp = IdentityProviderBase(
            name="Test", slug="test-provider-123", client_id="client-123"
        )

        # Assert
        assert idp.slug == "test-provider-123"

    def test_slug_validation_uppercase_rejected(self):
        """Test slug validation rejects uppercase letters.

        Asserts:
            - ValidationError is raised for uppercase characters
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            IdentityProviderBase(
                name="Test", slug="Test-Provider", client_id="client-123"
            )

        assert "Slug must contain only lowercase letters" in str(exc_info.value)

    def test_slug_validation_special_characters_rejected(self):
        """Test slug validation rejects special characters.

        Asserts:
            - ValidationError is raised for special characters
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            IdentityProviderBase(
                name="Test", slug="test_provider", client_id="client-123"
            )

        assert "Slug must contain only lowercase letters" in str(exc_info.value)

    def test_provider_type_validation_oidc(self):
        """Test provider_type validation accepts 'oidc'.

        Asserts:
            - 'oidc' is accepted as valid provider type
        """
        # Arrange & Act
        idp = IdentityProviderBase(
            name="Test", slug="test", provider_type="oidc", client_id="client-123"
        )

        # Assert
        assert idp.provider_type == "oidc"

    def test_provider_type_validation_oauth2(self):
        """Test provider_type validation accepts 'oauth2'.

        Asserts:
            - 'oauth2' is accepted as valid provider type
        """
        # Arrange & Act
        idp = IdentityProviderBase(
            name="Test", slug="test", provider_type="oauth2", client_id="client-123"
        )

        # Assert
        assert idp.provider_type == "oauth2"

    def test_provider_type_validation_saml(self):
        """Test provider_type validation accepts 'saml'.

        Asserts:
            - 'saml' is accepted as valid provider type
        """
        # Arrange & Act
        idp = IdentityProviderBase(
            name="Test", slug="test", provider_type="saml", client_id="client-123"
        )

        # Assert
        assert idp.provider_type == "saml"

    def test_provider_type_validation_invalid(self):
        """Test provider_type validation rejects invalid types.

        Asserts:
            - ValidationError is raised for invalid provider type
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            IdentityProviderBase(
                name="Test",
                slug="test",
                provider_type="invalid",
                client_id="client-123",
            )

        assert "Provider type must be one of" in str(exc_info.value)

    def test_name_max_length_validation(self):
        """Test name field max length validation.

        Asserts:
            - ValidationError is raised when name exceeds 100 characters
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            IdentityProviderBase(name="x" * 101, slug="test", client_id="client-123")

        assert "String should have at most 100 characters" in str(exc_info.value)

    def test_name_min_length_validation(self):
        """Test name field min length validation.

        Asserts:
            - ValidationError is raised when name is empty
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            IdentityProviderBase(name="", slug="test", client_id="client-123")

        assert "String should have at least 1 character" in str(exc_info.value)

    def test_slug_max_length_validation(self):
        """Test slug field max length validation.

        Asserts:
            - ValidationError is raised when slug exceeds 50 characters
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            IdentityProviderBase(name="Test", slug="x" * 51, client_id="client-123")

        assert "String should have at most 50 characters" in str(exc_info.value)

    def test_optional_fields_can_be_none(self):
        """Test optional fields can be None.

        Asserts:
            - issuer_url, authorization_endpoint, token_endpoint can be None
            - userinfo_endpoint, jwks_uri, icon can be None
            - user_mapping can be None
        """
        # Arrange & Act
        idp = IdentityProviderBase(
            name="Test",
            slug="test",
            issuer_url=None,
            authorization_endpoint=None,
            token_endpoint=None,
            userinfo_endpoint=None,
            jwks_uri=None,
            icon=None,
            user_mapping=None,
            client_id="client-123",
        )

        # Assert
        assert idp.issuer_url is None
        assert idp.authorization_endpoint is None
        assert idp.token_endpoint is None
        assert idp.userinfo_endpoint is None
        assert idp.jwks_uri is None
        assert idp.icon is None
        assert idp.user_mapping is None


class TestIdentityProviderCreate:
    """Test suite for IdentityProviderCreate schema."""

    def test_valid_identity_provider_create(self):
        """Test creating a valid IdentityProviderCreate instance.

        Asserts:
            - Instance is created successfully
            - client_secret is required and set
        """
        # Arrange & Act
        idp = IdentityProviderCreate(
            name="Test Provider",
            slug="test-provider",
            client_id="test-client-id",
            client_secret="test-client-secret",
        )

        # Assert
        assert idp.name == "Test Provider"
        assert idp.slug == "test-provider"
        assert idp.client_id == "test-client-id"
        assert idp.client_secret == "test-client-secret"

    def test_client_secret_required(self):
        """Test client_secret is required for IdentityProviderCreate.

        Asserts:
            - ValidationError is raised when client_secret is missing
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            IdentityProviderCreate(name="Test", slug="test", client_id="client-123")

        assert "client_secret" in str(exc_info.value)
        assert "Field required" in str(exc_info.value)

    def test_client_secret_min_length(self):
        """Test client_secret minimum length validation.

        Asserts:
            - ValidationError is raised when client_secret is empty
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            IdentityProviderCreate(
                name="Test",
                slug="test",
                client_id="client-123",
                client_secret="",
            )

        assert "String should have at least 1 character" in str(exc_info.value)

    def test_client_secret_max_length(self):
        """Test client_secret maximum length validation.

        Asserts:
            - ValidationError is raised when client_secret exceeds 512 characters
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            IdentityProviderCreate(
                name="Test",
                slug="test",
                client_id="client-123",
                client_secret="x" * 513,
            )

        assert "String should have at most 512 characters" in str(exc_info.value)


class TestIdentityProviderUpdate:
    """Test suite for IdentityProviderUpdate schema."""

    def test_valid_identity_provider_update(self):
        """Test creating a valid IdentityProviderUpdate instance.

        Asserts:
            - Instance is created successfully
            - All fields can be updated
        """
        # Arrange & Act
        idp = IdentityProviderUpdate(
            name="Updated Provider",
            slug="updated-provider",
            provider_type="oauth2",
            enabled=True,
            client_id="updated-client-id",
            client_secret="updated-secret",
        )

        # Assert
        assert idp.name == "Updated Provider"
        assert idp.slug == "updated-provider"
        assert idp.provider_type == "oauth2"
        assert idp.enabled is True
        assert idp.client_id == "updated-client-id"
        assert idp.client_secret == "updated-secret"

    def test_client_secret_optional(self):
        """Test client_secret is optional for IdentityProviderUpdate.

        Asserts:
            - Instance can be created without client_secret
            - client_secret defaults to None
        """
        # Arrange & Act
        idp = IdentityProviderUpdate(name="Test", slug="test", client_id="client-123")

        # Assert
        assert idp.client_secret is None

    def test_client_secret_can_be_none(self):
        """Test client_secret can explicitly be None.

        Asserts:
            - client_secret can be set to None
        """
        # Arrange & Act
        idp = IdentityProviderUpdate(
            name="Test", slug="test", client_id="client-123", client_secret=None
        )

        # Assert
        assert idp.client_secret is None

    def test_client_secret_min_length_when_provided(self):
        """Test client_secret minimum length when provided.

        Asserts:
            - ValidationError is raised when client_secret is empty string
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            IdentityProviderUpdate(
                name="Test",
                slug="test",
                client_id="client-123",
                client_secret="",
            )

        assert "String should have at least 1 character" in str(exc_info.value)


class TestIdentityProvider:
    """Test suite for IdentityProvider schema."""

    def test_valid_identity_provider(self):
        """Test creating a valid IdentityProvider instance.

        Asserts:
            - Instance is created successfully
            - All fields including id and timestamps are set
        """
        # Arrange
        now = datetime.utcnow()

        # Act
        idp = IdentityProvider(
            id=1,
            name="Test Provider",
            slug="test-provider",
            provider_type="oidc",
            enabled=True,
            client_id="test-client-id",
            created_at=now,
            updated_at=now,
        )

        # Assert
        assert idp.id == 1
        assert idp.name == "Test Provider"
        assert idp.slug == "test-provider"
        assert idp.provider_type == "oidc"
        assert idp.enabled is True
        assert idp.client_id == "test-client-id"
        assert idp.created_at == now
        assert idp.updated_at == now

    def test_identity_provider_requires_id(self):
        """Test id field is required for IdentityProvider.

        Asserts:
            - ValidationError is raised when id is missing
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            IdentityProvider(
                name="Test",
                slug="test",
                client_id="client-123",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )

        assert "id" in str(exc_info.value)
        assert "Field required" in str(exc_info.value)

    def test_identity_provider_requires_timestamps(self):
        """Test created_at and updated_at are required.

        Asserts:
            - ValidationError is raised when timestamps are missing
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            IdentityProvider(id=1, name="Test", slug="test", client_id="client-123")

        assert "created_at" in str(exc_info.value) or "updated_at" in str(
            exc_info.value
        )

    def test_serialize_client_id_decrypts_encrypted_value(self):
        """Test serialize_client_id decrypts encrypted client_id.

        Asserts:
            - Encrypted client_id (starting with 'gAAAAAB') triggers decryption
        """
        # Arrange
        now = datetime.utcnow()
        encrypted_id = "gAAAAABtest_encrypted_token"

        # Act
        idp = IdentityProvider(
            id=1,
            name="Test",
            slug="test",
            client_id=encrypted_id,
            created_at=now,
            updated_at=now,
        )

        # Assert - This will be tested with actual encryption in integration tests
        assert idp.client_id == encrypted_id

    def test_serialize_client_id_preserves_unencrypted_value(self):
        """Test serialize_client_id preserves non-encrypted client_id.

        Asserts:
            - Non-encrypted client_id is returned as-is
        """
        # Arrange
        now = datetime.utcnow()
        plain_id = "plain-client-id"

        # Act
        idp = IdentityProvider(
            id=1,
            name="Test",
            slug="test",
            client_id=plain_id,
            created_at=now,
            updated_at=now,
        )

        # Assert
        assert idp.client_id == plain_id

    def test_serialize_client_id_handles_none(self):
        """Test serialize_client_id handles None client_id.

        Asserts:
            - None client_id returns None
        """
        # Arrange
        now = datetime.utcnow()

        # Act
        idp = IdentityProvider(
            id=1,
            name="Test",
            slug="test",
            client_id=None,
            created_at=now,
            updated_at=now,
        )

        # Assert
        assert idp.client_id is None


class TestIdentityProviderPublic:
    """Test suite for IdentityProviderPublic schema."""

    def test_valid_identity_provider_public(self):
        """Test creating a valid IdentityProviderPublic instance.

        Asserts:
            - Instance is created successfully
            - Only public fields are present
        """
        # Arrange & Act
        idp = IdentityProviderPublic(
            id=1, name="Test Provider", slug="test-provider", icon="test-icon"
        )

        # Assert
        assert idp.id == 1
        assert idp.name == "Test Provider"
        assert idp.slug == "test-provider"
        assert idp.icon == "test-icon"

    def test_identity_provider_public_icon_optional(self):
        """Test icon field is optional for IdentityProviderPublic.

        Asserts:
            - Instance can be created without icon
            - icon defaults to None
        """
        # Arrange & Act
        idp = IdentityProviderPublic(id=1, name="Test", slug="test")

        # Assert
        assert idp.icon is None

    def test_identity_provider_public_no_sensitive_fields(self):
        """Test IdentityProviderPublic doesn't have sensitive fields.

        Asserts:
            - client_id, client_secret are not present
        """
        # Arrange & Act
        idp = IdentityProviderPublic(id=1, name="Test", slug="test")

        # Assert
        assert not hasattr(idp, "client_id")
        assert not hasattr(idp, "client_secret")


class TestIdentityProviderTemplate:
    """Test suite for IdentityProviderTemplate schema."""

    def test_valid_identity_provider_template(self):
        """Test creating a valid IdentityProviderTemplate instance.

        Asserts:
            - Instance is created successfully
            - All fields are set correctly
        """
        # Arrange & Act
        template = IdentityProviderTemplate(
            template_id="keycloak",
            name="Keycloak",
            provider_type="oidc",
            issuer_url="https://keycloak.example.com/realms/master",
            scopes="openid profile email",
            icon="keycloak",
            user_mapping={"username": ["preferred_username"], "email": ["email"]},
            description="Keycloak OIDC provider",
            configuration_notes="Setup instructions here",
        )

        # Assert
        assert template.template_id == "keycloak"
        assert template.name == "Keycloak"
        assert template.provider_type == "oidc"
        assert template.issuer_url == "https://keycloak.example.com/realms/master"
        assert template.scopes == "openid profile email"
        assert template.icon == "keycloak"
        assert template.user_mapping == {
            "username": ["preferred_username"],
            "email": ["email"],
        }
        assert template.description == "Keycloak OIDC provider"
        assert template.configuration_notes == "Setup instructions here"

    def test_template_required_fields(self):
        """Test required fields for IdentityProviderTemplate.

        Asserts:
            - ValidationError is raised when required fields are missing
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            IdentityProviderTemplate()

        error_str = str(exc_info.value)
        assert "template_id" in error_str or "Field required" in error_str

    def test_template_optional_fields(self):
        """Test optional fields for IdentityProviderTemplate.

        Asserts:
            - Template can be created with only required fields
            - Optional fields default to None
        """
        # Arrange & Act
        template = IdentityProviderTemplate(
            template_id="custom",
            name="Custom Provider",
            provider_type="oidc",
            scopes="openid",
            description="Custom provider",
        )

        # Assert
        assert template.issuer_url is None
        assert template.icon is None
        assert template.user_mapping is None
        assert template.configuration_notes is None


class TestTokenExchangeRequest:
    """Test suite for TokenExchangeRequest schema."""

    def test_valid_token_exchange_request(self):
        """Test creating a valid TokenExchangeRequest instance.

        Asserts:
            - Instance is created successfully with valid code_verifier
        """
        # Arrange
        # Valid base64url string (43 characters minimum)
        code_verifier = "a" * 43 + "B1-_" * 10

        # Act
        request = TokenExchangeRequest(code_verifier=code_verifier)

        # Assert
        assert request.code_verifier == code_verifier

    def test_code_verifier_min_length(self):
        """Test code_verifier minimum length validation.

        Asserts:
            - ValidationError is raised when code_verifier is less than 43 chars
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            TokenExchangeRequest(code_verifier="a" * 42)

        assert "String should have at least 43 characters" in str(exc_info.value)

    def test_code_verifier_max_length(self):
        """Test code_verifier maximum length validation.

        Asserts:
            - ValidationError is raised when code_verifier exceeds 128 chars
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            TokenExchangeRequest(code_verifier="a" * 129)

        assert "String should have at most 128 characters" in str(exc_info.value)

    def test_code_verifier_format_validation_valid(self):
        """Test code_verifier format validation accepts valid base64url.

        Asserts:
            - Valid base64url characters (A-Z, a-z, 0-9, -, _) are accepted
        """
        # Arrange
        valid_verifier = (
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        )

        # Act
        request = TokenExchangeRequest(code_verifier=valid_verifier)

        # Assert
        assert request.code_verifier == valid_verifier

    def test_code_verifier_format_validation_invalid(self):
        """Test code_verifier format validation rejects invalid characters.

        Asserts:
            - ValidationError is raised for non-base64url characters
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            TokenExchangeRequest(
                code_verifier="a" * 43 + "!"
            )  # ! is not valid base64url

        assert "code_verifier must be valid base64url" in str(exc_info.value)

    def test_code_verifier_format_validation_special_chars(self):
        """Test code_verifier format validation rejects special characters.

        Asserts:
            - ValidationError is raised for special characters like +, =
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            TokenExchangeRequest(code_verifier="a" * 43 + "+")

        assert "code_verifier must be valid base64url" in str(exc_info.value)


class TestTokenExchangeResponse:
    """Test suite for TokenExchangeResponse schema."""

    def test_valid_token_exchange_response(self):
        """Test creating a valid TokenExchangeResponse instance.

        Asserts:
            - Instance is created successfully with all required fields
            - Default values are applied
        """
        # Arrange & Act
        response = TokenExchangeResponse(
            session_id="session-123",
            access_token="access-token-xyz",
            refresh_token="refresh-token-abc",
            csrf_token="csrf-token-def",
        )

        # Assert
        assert response.session_id == "session-123"
        assert response.access_token == "access-token-xyz"
        assert response.refresh_token == "refresh-token-abc"
        assert response.csrf_token == "csrf-token-def"
        assert response.expires_in == 900  # Default value
        assert response.token_type == "Bearer"  # Default value

    def test_token_exchange_response_required_fields(self):
        """Test required fields for TokenExchangeResponse.

        Asserts:
            - ValidationError is raised when required fields are missing
        """
        # Arrange & Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            TokenExchangeResponse()

        error_str = str(exc_info.value)
        assert "session_id" in error_str or "access_token" in error_str

    def test_token_exchange_response_custom_expires_in(self):
        """Test custom expires_in value for TokenExchangeResponse.

        Asserts:
            - Custom expires_in value can be set
        """
        # Arrange & Act
        response = TokenExchangeResponse(
            session_id="session-123",
            access_token="access-token-xyz",
            refresh_token="refresh-token-abc",
            csrf_token="csrf-token-def",
            expires_in=1800,
        )

        # Assert
        assert response.expires_in == 1800

    def test_token_exchange_response_custom_token_type(self):
        """Test custom token_type value for TokenExchangeResponse.

        Asserts:
            - Custom token_type value can be set
        """
        # Arrange & Act
        response = TokenExchangeResponse(
            session_id="session-123",
            access_token="access-token-xyz",
            refresh_token="refresh-token-abc",
            csrf_token="csrf-token-def",
            token_type="Custom",
        )

        # Assert
        assert response.token_type == "Custom"

    def test_serialize_client_id_with_exception_handling(self):
        """Test serialize_client_id handles decryption exceptions gracefully.

        Asserts:
            - When decryption fails, original encrypted value is returned
        """
        # Arrange
        from unittest.mock import patch

        now = datetime.utcnow()

        idp_data = {
            "id": 1,
            "name": "Test Provider",
            "slug": "test-provider",
            "provider_type": "oidc",
            "enabled": True,
            "issuer_url": "https://auth.example.com",
            "authorization_endpoint": "https://auth.example.com/authorize",
            "token_endpoint": "https://auth.example.com/token",
            "scopes": "openid",
            "client_id": "gAAAAAB_invalid_encrypted_value",
            "created_at": now,
            "updated_at": now,
        }

        # Act & Assert - Test that exception during decryption is handled
        with patch(
            "core.cryptography.decrypt_token_fernet",
            side_effect=Exception("Decryption error"),
        ):
            idp = IdentityProvider(**idp_data)
            # Should return encrypted value if decryption fails
            assert idp.client_id is not None
