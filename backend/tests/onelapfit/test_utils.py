"""Tests for onelapfit.utils module."""

import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import httpx
from fastapi import HTTPException

from users.users_integrations.models import UsersIntegrations
import onelapfit.utils as onelapfit_utils


class TestGenerateNonce:
    """Test suite for generate_nonce function."""

    def test_generate_nonce_returns_string(self):
        """Test that generate_nonce returns a string.

        Asserts:
            - Return value is a string
        """
        # Act
        result = onelapfit_utils.generate_nonce()

        # Assert
        assert isinstance(result, str)

    def test_generate_nonce_length(self):
        """Test that generate_nonce returns an 8-character Base64 string.

        6 random bytes encoded as Base64 produce exactly 8 characters
        (6 bytes * 4/3 = 8, no padding needed when multiple of 3).

        Asserts:
            - Length is 8
        """
        # Act
        result = onelapfit_utils.generate_nonce()

        # Assert
        assert len(result) == 8

    def test_generate_nonce_uniqueness(self):
        """Test that successive calls return different values.

        Asserts:
            - Two consecutive nonces are not equal
        """
        # Act
        nonce1 = onelapfit_utils.generate_nonce()
        nonce2 = onelapfit_utils.generate_nonce()

        # Assert
        assert nonce1 != nonce2


class TestCreateSignature:
    """Test suite for create_signature function."""

    def test_create_signature_deterministic(self):
        """Test that create_signature returns the expected MD5 for known inputs.

        Asserts:
            - Output matches the manually computed MD5 of the sign string
        """
        # Arrange
        path = "/api/v1/app/login"
        params = {"nonce": "abc123", "timestamp": "1000"}
        api_key = onelapfit_utils.ONELAPFIT_API_KEY
        expected_sign_string = (
            f"{path}?nonce=abc123&timestamp=1000&key={api_key}"
        )
        expected = hashlib.md5(expected_sign_string.encode("utf-8")).hexdigest()

        # Act
        result = onelapfit_utils.create_signature(path, params)

        # Assert
        assert result == expected

    def test_create_signature_sorts_params_alphabetically(self):
        """Test that params are sorted alphabetically before hashing.

        Providing params in reverse order must produce the same signature
        as providing them in alphabetical order.

        Asserts:
            - Signature is identical regardless of input dict ordering
        """
        # Arrange
        path = "/api/v1/app/record/riding/list"
        params_forward = {"end_time": "2000", "nonce": "xyz", "start_time": "1000", "timestamp": "999"}
        params_reversed = {"timestamp": "999", "start_time": "1000", "nonce": "xyz", "end_time": "2000"}

        # Act
        sig_forward = onelapfit_utils.create_signature(path, params_forward)
        sig_reversed = onelapfit_utils.create_signature(path, params_reversed)

        # Assert
        assert sig_forward == sig_reversed

    def test_create_signature_returns_hex_string(self):
        """Test that create_signature returns a lowercase hex string.

        Asserts:
            - Result is a 32-character lowercase hex string (MD5 digest)
        """
        # Arrange
        path = "/api/v1/app/login"
        params = {"nonce": "abc", "timestamp": "123"}

        # Act
        result = onelapfit_utils.create_signature(path, params)

        # Assert
        assert len(result) == 32
        assert result == result.lower()
        assert all(c in "0123456789abcdef" for c in result)


class TestHashPassword:
    """Test suite for hash_password function."""

    def test_hash_password_known_value(self):
        """Test that hash_password returns the correct MD5 hex digest.

        Asserts:
            - Result matches the MD5 hex digest of the input password
        """
        # Arrange
        password = "testpassword"
        expected = hashlib.md5(password.encode()).hexdigest().lower()

        # Act
        result = onelapfit_utils.hash_password(password)

        # Assert
        assert result == expected

    def test_hash_password_is_lowercase(self):
        """Test that hash_password always returns lowercase hex.

        Asserts:
            - Result is all lowercase
        """
        # Act
        result = onelapfit_utils.hash_password("AnyPassword123!")

        # Assert
        assert result == result.lower()

    def test_hash_password_returns_32_chars(self):
        """Test that hash_password returns a 32-character string.

        Asserts:
            - Result length is 32 (MD5 hex digest length)
        """
        # Act
        result = onelapfit_utils.hash_password("somepassword")

        # Assert
        assert len(result) == 32


class TestFetchUserIntegrationsAndValidateToken:
    """Test suite for fetch_user_integrations_and_validate_token function."""

    def test_success_returns_integrations(self, mock_db):
        """Test that valid integrations with a token are returned.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns the UsersIntegrations object when token is present
        """
        # Arrange
        mock_integrations = MagicMock(spec=UsersIntegrations)
        mock_integrations.onelapfit_token = "some_encrypted_token"

        with patch(
            "onelapfit.utils.user_integrations_crud"
            ".get_user_integrations_by_user_id"
        ) as mock_get:
            mock_get.return_value = mock_integrations

            # Act
            result = onelapfit_utils.fetch_user_integrations_and_validate_token(
                1, mock_db
            )

        # Assert
        assert result == mock_integrations

    def test_token_none_returns_none(self, mock_db):
        """Test that None is returned when the OneLapFit token is missing.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns None when onelapfit_token is None
        """
        # Arrange
        mock_integrations = MagicMock(spec=UsersIntegrations)
        mock_integrations.onelapfit_token = None

        with patch(
            "onelapfit.utils.user_integrations_crud"
            ".get_user_integrations_by_user_id"
        ) as mock_get:
            mock_get.return_value = mock_integrations

            # Act
            result = onelapfit_utils.fetch_user_integrations_and_validate_token(
                1, mock_db
            )

        # Assert
        assert result is None

    def test_user_integrations_not_found_raises_404(self, mock_db):
        """Test that a 404 HTTPException is raised when integrations are not found.

        Args:
            mock_db: Mocked database session

        Asserts:
            - HTTPException with 404 status code is raised
        """
        # Arrange
        with patch(
            "onelapfit.utils.user_integrations_crud"
            ".get_user_integrations_by_user_id"
        ) as mock_get:
            mock_get.return_value = None

            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                onelapfit_utils.fetch_user_integrations_and_validate_token(
                    1, mock_db
                )

            assert exc_info.value.status_code == 404


class TestGetRegionCode:
    """Test suite for get_region_code async function."""

    async def test_returns_region_on_success(self):
        """Test that the region code string is returned on a successful API response.

        Asserts:
            - Returns the region code from the API response data
        """
        # Arrange
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 200,
            "data": {"region": "EU"},
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch("onelapfit.utils.httpx.AsyncClient", return_value=mock_async_client):
            # Act
            result = await onelapfit_utils.get_region_code("user@example.com")

        # Assert
        assert result == "EU"

    async def test_raises_401_on_non_200_http_status(self):
        """Test that a 401 HTTPException is raised when the HTTP response is not 200.

        Asserts:
            - HTTPException with status 401 is raised
        """
        # Arrange
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 403
        mock_response.text = "Forbidden"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch("onelapfit.utils.httpx.AsyncClient", return_value=mock_async_client):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await onelapfit_utils.get_region_code("user@example.com")

        assert exc_info.value.status_code == 401

    async def test_raises_502_on_request_error(self):
        """Test that a 502 HTTPException is raised on a network-level request error.

        Asserts:
            - HTTPException with status 502 is raised when httpx raises RequestError
        """
        # Arrange
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.RequestError("connection failed")
        )
        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch("onelapfit.utils.httpx.AsyncClient", return_value=mock_async_client):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await onelapfit_utils.get_region_code("user@example.com")

        assert exc_info.value.status_code == 502


class TestLoginOneLapFit:
    """Test suite for login_onelapfit async function."""

    async def test_returns_token_and_region_on_success(self):
        """Test that (token, region_code) tuple is returned on successful login.

        Asserts:
            - Returns a 2-tuple (token_string, region_string)
        """
        # Arrange
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 200,
            "data": {"token": "test_token_abc"},
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "onelapfit.utils.get_region_code", new=AsyncMock(return_value="EU")
        ), patch("onelapfit.utils.httpx.AsyncClient", return_value=mock_async_client):
            # Act
            token, region = await onelapfit_utils.login_onelapfit(
                "user@example.com", "password"
            )

        # Assert
        assert token == "test_token_abc"
        assert region == "EU"

    async def test_raises_401_when_api_code_not_200(self):
        """Test that a 401 HTTPException is raised when the API body code is not 200.

        Asserts:
            - HTTPException with status 401 is raised
        """
        # Arrange
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 401,
            "error": "invalid credentials",
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "onelapfit.utils.get_region_code", new=AsyncMock(return_value="EU")
        ), patch("onelapfit.utils.httpx.AsyncClient", return_value=mock_async_client):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await onelapfit_utils.login_onelapfit("user@example.com", "password")

        assert exc_info.value.status_code == 401

    async def test_raises_502_on_request_error(self):
        """Test that a 502 HTTPException is raised on a network-level error during login.

        Asserts:
            - HTTPException with status 502 is raised when httpx raises RequestError
        """
        # Arrange
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=httpx.RequestError("network error")
        )
        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "onelapfit.utils.get_region_code", new=AsyncMock(return_value="EU")
        ), patch("onelapfit.utils.httpx.AsyncClient", return_value=mock_async_client):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await onelapfit_utils.login_onelapfit("user@example.com", "password")

        assert exc_info.value.status_code == 502


class TestFetchOneLapFitActivities:
    """Test suite for fetch_onelapfit_activities async function."""

    async def test_returns_data_on_success(self):
        """Test that the activities data dict is returned on a successful API response.

        Asserts:
            - Returns the 'data' key from the API JSON body
        """
        # Arrange
        activities_payload = {"days": {"1700000000": {"info": []}}}
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 200, "data": activities_payload}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch("onelapfit.utils.httpx.AsyncClient", return_value=mock_async_client):
            # Act
            result = await onelapfit_utils.fetch_onelapfit_activities(
                token="tok",
                start_time=1700000000,
                end_time=1700086400,
                region="EU",
            )

        # Assert
        assert result == activities_payload

    async def test_raises_424_on_non_200_http_status(self):
        """Test that a 424 HTTPException is raised when the HTTP status is not 200.

        Asserts:
            - HTTPException with status 424 is raised
        """
        # Arrange
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.text = "Server Error"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch("onelapfit.utils.httpx.AsyncClient", return_value=mock_async_client):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await onelapfit_utils.fetch_onelapfit_activities(
                    token="tok",
                    start_time=1700000000,
                    end_time=1700086400,
                )

        assert exc_info.value.status_code == 424

    async def test_raises_502_on_request_error(self):
        """Test that a 502 HTTPException is raised on a network-level request error.

        Asserts:
            - HTTPException with status 502 is raised when httpx raises RequestError
        """
        # Arrange
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.RequestError("timeout")
        )
        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch("onelapfit.utils.httpx.AsyncClient", return_value=mock_async_client):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await onelapfit_utils.fetch_onelapfit_activities(
                    token="tok",
                    start_time=1700000000,
                    end_time=1700086400,
                )

        assert exc_info.value.status_code == 502


class TestDownloadFitFile:
    """Test suite for download_fit_file async function."""

    async def test_returns_bytes_on_success(self):
        """Test that the raw FIT file bytes are returned on a successful download.

        Asserts:
            - Returns the response content as bytes
        """
        # Arrange
        fake_content = b"FIT_FILE_BYTES"
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.content = fake_content

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch("onelapfit.utils.httpx.AsyncClient", return_value=mock_async_client):
            # Act
            result = await onelapfit_utils.download_fit_file(
                "https://cdn.example.com/file.fit"
            )

        # Assert
        assert result == fake_content

    async def test_raises_424_on_non_200_http_status(self):
        """Test that a 424 HTTPException is raised when the download HTTP status is not 200.

        Asserts:
            - HTTPException with status 424 is raised
        """
        # Arrange
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 404

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch("onelapfit.utils.httpx.AsyncClient", return_value=mock_async_client):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await onelapfit_utils.download_fit_file(
                    "https://cdn.example.com/missing.fit"
                )

        assert exc_info.value.status_code == 424

    async def test_raises_502_on_request_error(self):
        """Test that a 502 HTTPException is raised on a network-level error during download.

        Asserts:
            - HTTPException with status 502 is raised when httpx raises RequestError
        """
        # Arrange
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.RequestError("connection refused")
        )
        mock_async_client = MagicMock()
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=False)

        with patch("onelapfit.utils.httpx.AsyncClient", return_value=mock_async_client):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                await onelapfit_utils.download_fit_file(
                    "https://cdn.example.com/file.fit"
                )

        assert exc_info.value.status_code == 502
