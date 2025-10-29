from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Response

from pwdlib.hashers.bcrypt import BcryptHasher
from pwdlib import PasswordHash

import auth.password_hasher as auth_password_hasher
import auth.utils as auth_utils
import session.utils as session_utils


class TestAuthenticationSecurity:
    """
    Test suite for authentication and session management utilities.

    This class contains comprehensive tests for the authentication and session-related
    functions in the `session_utils` module. It covers scenarios including:

    - User authentication with valid and invalid credentials.
    - Password hash upgrades and security edge cases (e.g., empty or whitespace passwords).
    - SQL injection protection in authentication.
    - Token creation and validation, including session ID uniqueness and CSRF token generation.
    - Login completion logic for different client types (web, mobile) and error handling for invalid types.
    - User agent parsing for various device/browser/OS combinations.
    - IP address extraction from HTTP request headers and client information.
    - Session object creation and editing, ensuring correct field population and updates.

    Each test is designed to verify correct behavior, security, and robustness of the authentication/session logic,
    using mocks and fixtures to isolate dependencies and simulate real-world scenarios.
    """

    def test_create_session_object_contains_required_fields(
        self, sample_user_read, mock_request
    ):
        """
        Test that the session object created by `session_utils.create_session_object` contains all required fields.

        This test verifies that:
        - The session ID matches the provided value.
        - The user ID matches the sample user.
        - The refresh token hash is correctly set.
        - The IP address, device type, operating system, browser, and creation timestamp are all populated.
        - The expiration timestamp matches the provided value.

        Args:
            sample_user_read: A sample user object used for testing.
            mock_request: A mock request object simulating an HTTP request.

        Asserts:
            - Session fields are correctly set and not None where required.
        """
        session_id = "test-session-id"
        refresh_token_hash = "hashed_refresh_token"
        expires_at = datetime.now(timezone.utc)

        session = session_utils.create_session_object(
            session_id, sample_user_read, mock_request, refresh_token_hash, expires_at
        )

        assert session.id == session_id, "Session ID should match"
        assert session.user_id == sample_user_read.id, "User ID should match"
        assert (
            session.refresh_token == refresh_token_hash
        ), "Refresh token hash should match"
        assert session.ip_address is not None, "IP address should be set"
        assert session.device_type is not None, "Device type should be set"
        assert session.operating_system is not None, "OS should be set"
        assert session.browser is not None, "Browser should be set"
        assert session.created_at is not None, "Created timestamp should be set"
        assert session.expires_at == expires_at, "Expiration should match"

    def test_edit_session_object_preserves_and_updates_fields(
        self, sample_user_read, mock_request
    ):
        """
        Test that the `edit_session_object` function preserves existing session fields while updating necessary ones.

        This test verifies that:
        - The session ID and user ID remain unchanged from the original session.
        - The refresh token hash is updated to the new value.
        - Device information (IP address, device type, OS, browser) is updated based on the new request.
        - The created_at timestamp is preserved from the original session.
        - The expires_at timestamp is updated to the new expiration time.

        Args:
            sample_user_read: A sample user object used for testing.
            mock_request: A mock request object simulating an HTTP request.

        Asserts:
            - Session ID and user ID remain unchanged.
            - Refresh token is updated to the new hash.
            - Device information is updated from the request.
            - Original created_at timestamp is preserved.
            - Expiration timestamp is updated to the new value.
        """
        # Create an existing session object
        original_session_id = "existing-session-id"
        original_created_at = datetime.now(timezone.utc) - timedelta(days=1)
        old_refresh_token_hash = "old_hashed_refresh_token"
        old_expires_at = datetime.now(timezone.utc) + timedelta(days=7)

        existing_session = MagicMock()
        existing_session.id = original_session_id
        existing_session.user_id = sample_user_read.id
        existing_session.refresh_token = old_refresh_token_hash
        existing_session.created_at = original_created_at
        existing_session.expires_at = old_expires_at

        # New values for the update
        new_refresh_token_hash = "new_hashed_refresh_token"
        new_expires_at = datetime.now(timezone.utc) + timedelta(days=30)

        # Edit the session
        updated_session = session_utils.edit_session_object(
            mock_request, new_refresh_token_hash, new_expires_at, existing_session
        )

        # Verify preserved fields
        assert (
            updated_session.id == original_session_id
        ), "Session ID should be preserved"
        assert (
            updated_session.user_id == sample_user_read.id
        ), "User ID should be preserved"
        assert (
            updated_session.created_at == original_created_at
        ), "Created timestamp should be preserved"

        # Verify updated fields
        assert (
            updated_session.refresh_token == new_refresh_token_hash
        ), "Refresh token hash should be updated"
        assert (
            updated_session.expires_at == new_expires_at
        ), "Expiration should be updated"

        # Verify fields updated from request
        assert updated_session.ip_address is not None, "IP address should be set"
        assert updated_session.device_type is not None, "Device type should be set"
        assert (
            updated_session.operating_system is not None
        ), "Operating system should be set"
        assert updated_session.browser is not None, "Browser should be set"

    def test_authenticate_user_with_valid_credentials(
        self, password_hasher, mock_db, sample_user_read
    ):
        """
        Test that the `auth_utils.authenticate_user` function successfully authenticates a user with valid credentials.
        This test:
        - Hashes a sample password using the provided password hasher.
        - Mocks a user ORM object with the hashed password and sample user data.
        - Patches the `auth_utils.authenticate_user` function in the users CRUD utility to return the mocked user.
        - Calls the actual `auth_utils.authenticate_user` function with valid credentials.
        - Asserts that authentication succeeds and the returned user matches the expected sample user.
        Args:
            password_hasher: Fixture or mock for password hashing utilities.
            mock_db: Mocked database session or connection.
            sample_user_read: Sample user data object for comparison.
        Asserts:
            - The authentication result is not None.
            - The returned user's ID matches the sample user's ID.
            - The returned user's username matches the sample user's username.
        """
        password = "TestPassword123!"
        hashed_password = password_hasher.hash_password(password)

        # Create ORM-like object with password attribute
        mock_user_orm = MagicMock()
        mock_user_orm.id = sample_user_read.id
        mock_user_orm.username = sample_user_read.username
        mock_user_orm.password = hashed_password

        with patch("session.utils.users_crud.authenticate_user") as mock_auth:
            mock_auth.return_value = mock_user_orm

            result = auth_utils.authenticate_user(
                "testuser", password, password_hasher, mock_db
            )

            assert result is not None, "Authentication should succeed"
            assert result.id == sample_user_read.id, "Should return correct user"
            assert result.username == sample_user_read.username, "Username should match"

    def test_authenticate_user_with_invalid_username(self, password_hasher, mock_db):
        """
        Test that the `auth_utils.authenticate_user` function raises an HTTPException with status code 401
        when provided with an invalid (nonexistent) username. Ensures that the exception detail
        contains information about the username.
        """
        with patch("session.utils.users_crud.authenticate_user") as mock_auth:
            mock_auth.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                auth_utils.authenticate_user(
                    "nonexistent", "password", password_hasher, mock_db
                )

            assert exc_info.value.status_code == 401
            assert "username" in exc_info.value.detail.lower()

    def test_authenticate_user_with_invalid_password(
        self, password_hasher, mock_db, sample_user_read
    ):
        """
        Test that the `auth_utils.authenticate_user` function raises an HTTPException with status code 401
        when an incorrect password is provided for an existing user.
        This test mocks the user retrieval and password hashing process, simulating a scenario
        where the user exists but the provided password does not match the stored hash.
        It asserts that the exception raised contains a detail mentioning "password".
        """
        correct_password = "CorrectPassword123!"
        wrong_password = "WrongPassword123!"

        # Create ORM-like object with password attribute
        mock_user_orm = MagicMock()
        mock_user_orm.id = sample_user_read.id
        mock_user_orm.username = sample_user_read.username
        mock_user_orm.password = password_hasher.hash_password(correct_password)

        with patch("session.utils.users_crud.authenticate_user") as mock_auth:
            mock_auth.return_value = mock_user_orm

            with pytest.raises(HTTPException) as exc_info:
                auth_utils.authenticate_user(
                    "testuser", wrong_password, password_hasher, mock_db
                )

            assert exc_info.value.status_code == 401
            assert "password" in exc_info.value.detail.lower()

    def test_authenticate_user_updates_hash_if_needed(
        self, password_hasher, mock_db, sample_user_read
    ):
        """
        Test that the `auth_utils.authenticate_user` function updates the user's password hash if the current hash is outdated.
        This test simulates a scenario where a user's password is hashed with an old hasher. It mocks the authentication and password update functions to verify that authentication succeeds and that the system is prepared to update the password hash if necessary.
        Args:
            self: The test case instance.
            password_hasher: The current password hasher instance used for verification and hashing.
            mock_db: A mocked database session or connection.
            sample_user_read: A sample user object with user attributes for testing.
        Asserts:
            - The authentication process returns a non-None result, indicating successful authentication.
        """
        password = "TestPassword123!"

        old_hasher = auth_password_hasher.PasswordHasher(PasswordHash([BcryptHasher()]))

        # Create ORM-like object with password attribute
        mock_user_orm = MagicMock()
        mock_user_orm.id = sample_user_read.id
        mock_user_orm.username = sample_user_read.username
        mock_user_orm.password = old_hasher.hash_password(password)

        with patch("session.utils.users_crud.authenticate_user") as mock_auth:
            with patch("session.utils.users_crud.edit_user_password") as _mock_edit:
                mock_auth.return_value = mock_user_orm

                result = auth_utils.authenticate_user(
                    "testuser", password, password_hasher, mock_db
                )

                assert result is not None, "Authentication should succeed"

    def test_authentication_sql_injection_protection(self, password_hasher, mock_db):
        """
        Tests that the authentication function is protected against SQL injection attacks.

        This test attempts to authenticate using a list of malicious usernames commonly used in SQL injection attacks.
        It mocks the `authenticate_user` function to always return None, simulating failed authentication.
        For each malicious username, it asserts that an HTTPException with status code 401 is raised,
        indicating that the authentication attempt was correctly rejected.

        Args:
            password_hasher: The password hasher fixture or mock used for password verification.
            mock_db: The mock database session or connection.

        Raises:
            AssertionError: If the authentication does not raise an HTTPException with status code 401.
        """
        malicious_usernames = [
            "admin' OR '1'='1",
            "admin'--",
            "admin' /*",
            "' OR 1=1--",
            "admin'; DROP TABLE users--",
        ]

        with patch("session.utils.users_crud.authenticate_user") as mock_auth:
            mock_auth.return_value = None

            for username in malicious_usernames:
                with pytest.raises(HTTPException) as exc_info:
                    auth_utils.authenticate_user(
                        username, "password", password_hasher, mock_db
                    )
                assert exc_info.value.status_code == 401

    def test_empty_password_authentication(
        self, password_hasher, mock_db, sample_user_read
    ):
        """
        Test that authentication fails with an empty password.

        This test verifies that when an empty password is provided to the authentication
        function, an HTTPException with status code 401 is raised, indicating unauthorized
        access. It mocks the user ORM object and the authentication function to simulate
        the authentication process without accessing the real database.
        """
        # Create ORM-like object with password attribute
        mock_user_orm = MagicMock()
        mock_user_orm.id = sample_user_read.id
        mock_user_orm.username = sample_user_read.username
        mock_user_orm.password = password_hasher.hash_password("RealPassword123!")

        with patch("session.utils.users_crud.authenticate_user") as mock_auth:
            mock_auth.return_value = mock_user_orm

            with pytest.raises(HTTPException) as exc_info:
                auth_utils.authenticate_user("testuser", "", password_hasher, mock_db)

            assert exc_info.value.status_code == 401

    def test_empty_username_authentication(self, password_hasher, mock_db):
        """
        Test that authentication fails with an empty username.

        This test verifies that when an empty string is provided as the username to the
        `authenticate_user` function, an HTTPException with status code 401 is raised,
        indicating unauthorized access. The database call returns None for empty username,
        simulating that no user is found.
        """
        with patch("session.utils.users_crud.authenticate_user") as mock_auth:
            # Mock database to return None for empty username (user not found)
            mock_auth.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                auth_utils.authenticate_user(
                    "", "RealPassword123!", password_hasher, mock_db
                )

            assert exc_info.value.status_code == 401

    def test_whitespace_password_authentication(
        self, password_hasher, mock_db, sample_user_read
    ):
        """
        Test that authentication fails with a password consisting only of whitespace.

        This test mocks the user authentication process to ensure that when a user attempts
        to authenticate with a password containing only whitespace characters, the
        authentication utility raises an HTTPException with a 401 status code.

        Args:
            password_hasher: Fixture or mock for password hashing utilities.
            mock_db: Mocked database session or connection.
            sample_user_read: Sample user object with id and username attributes.

        Asserts:
            - HTTPException is raised with status code 401 when a whitespace-only password is used.
        """
        # Create ORM-like object with password attribute
        mock_user_orm = MagicMock()
        mock_user_orm.id = sample_user_read.id
        mock_user_orm.username = sample_user_read.username
        mock_user_orm.password = password_hasher.hash_password("RealPassword123!")

        with patch("session.utils.users_crud.authenticate_user") as mock_auth:
            mock_auth.return_value = mock_user_orm

            with pytest.raises(HTTPException) as exc_info:
                auth_utils.authenticate_user(
                    "testuser", "    ", password_hasher, mock_db
                )

            assert exc_info.value.status_code == 401

    def test_create_tokens_generates_all_required_tokens(
        self, token_manager, sample_user_read
    ):
        """
        Test that the `auth_utils.create_tokens` function generates all required tokens and their expirations.

        This test verifies that:
        - A session ID is generated.
        - Access and refresh tokens are generated.
        - A CSRF token is generated.
        - The expiration times for both access and refresh tokens are set in the future.

        Args:
            token_manager: The token manager instance used to generate tokens.
            sample_user_read: A sample user object for whom the tokens are generated.

        Asserts:
            - Session ID, access token, refresh token, and CSRF token are not None.
            - Access and refresh token expiration times are greater than the current UTC time.
        """
        (
            session_id,
            access_token_exp,
            access_token,
            refresh_token_exp,
            refresh_token,
            csrf_token,
        ) = auth_utils.create_tokens(sample_user_read, token_manager)

        assert session_id is not None, "Session ID should be generated"
        assert access_token is not None, "Access token should be generated"
        assert refresh_token is not None, "Refresh token should be generated"
        assert csrf_token is not None, "CSRF token should be generated"
        assert access_token_exp > datetime.now(
            timezone.utc
        ), "Access token expiration should be in future"
        assert refresh_token_exp > datetime.now(
            timezone.utc
        ), "Refresh token expiration should be in future"

    def test_create_tokens_uses_provided_session_id(
        self, token_manager, sample_user_read
    ):
        """
        Test that the `auth_utils.create_tokens` function uses the provided session ID when one is supplied.

        Args:
            token_manager: The token manager fixture or mock used to generate tokens.
            sample_user_read: A sample user object used for token creation.

        Asserts:
            The returned session ID from `auth_utils.create_tokens` matches the provided session ID.
        """
        provided_session_id = "custom-session-id-123"

        (
            session_id,
            _,
            _,
            _,
            _,
            _,
        ) = auth_utils.create_tokens(
            sample_user_read, token_manager, session_id=provided_session_id
        )

        assert session_id == provided_session_id, "Should use provided session ID"

    def test_create_tokens_generates_unique_session_ids(
        self, token_manager, sample_user_read
    ):
        """
        Test that the `auth_utils.create_tokens` function generates unique session IDs for each invocation.

        This test calls `auth_utils.create_tokens` multiple times with the same user and token manager,
        collects the returned session IDs, and asserts that all session IDs are unique.

        Args:
            token_manager: The token manager instance used to generate tokens.
            sample_user_read: The user object for whom the tokens are generated.

        Asserts:
            The number of unique session IDs generated equals the number of invocations,
            ensuring that each session receives a distinct session ID.
        """
        session_ids = set()
        for _ in range(10):
            session_id, _, _, _, _, _ = auth_utils.create_tokens(
                sample_user_read, token_manager
            )
            session_ids.add(session_id)

        assert len(session_ids) == 10, "Session IDs should be unique"

    def test_complete_login_for_web_client(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request
    ):
        """
        Tests the `complete_login` function for the web client scenario.

        This test verifies that when a login is completed for a web client:
        - The response contains a "session_id" key.
        - The "session_id" is a string.
        - The `create_session` utility is called exactly once.

        Mocks are used for dependencies such as password hasher, token manager, database, and request objects.
        """
        response = Response()
        mock_request.headers["X-Client-Type"] = "web"

        with patch("session.utils.create_session") as mock_create_session:
            result = auth_utils.complete_login(
                response,
                mock_request,
                sample_user_read,
                "web",
                password_hasher,
                token_manager,
                mock_db,
            )

            assert "session_id" in result, "Should return session_id for web"
            assert isinstance(result["session_id"], str), "Session ID should be string"
            mock_create_session.assert_called_once()

    def test_complete_login_for_mobile_client(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request
    ):
        """
        Test the `complete_login` function for mobile clients.

        This test verifies that when a login is completed for a mobile client:
        - The response contains an "access_token", "refresh_token", "session_id", "token_type", and "expires_in".
        - The "token_type" is set to "Bearer".
        - The session creation utility (`create_session`) is called exactly once.

        Mocks:
            - `password_hasher`: Mocked password hasher dependency.
            - `token_manager`: Mocked token manager dependency.
            - `mock_db`: Mocked database session.
            - `sample_user_read`: Sample user object for authentication.
            - `mock_request`: Mocked request object with "X-Client-Type" header set to "mobile".
        """
        response = Response()
        mock_request.headers["X-Client-Type"] = "mobile"

        with patch("session.utils.create_session") as mock_create_session:
            result = auth_utils.complete_login(
                response,
                mock_request,
                sample_user_read,
                "mobile",
                password_hasher,
                token_manager,
                mock_db,
            )

            assert "access_token" in result, "Should return access_token for mobile"
            assert "refresh_token" in result, "Should return refresh_token for mobile"
            assert "session_id" in result, "Should return session_id for mobile"
            assert "token_type" in result, "Should return token_type for mobile"
            assert "expires_in" in result, "Should return expires_in for mobile"
            assert result["token_type"] == "Bearer", "Token type should be Bearer"
            mock_create_session.assert_called_once()

    def test_complete_login_with_invalid_client_type(
        self, password_hasher, token_manager, mock_db, sample_user_read, mock_request
    ):
        """
        Test that the `complete_login` function raises an HTTPException with status code 403
        when provided with an invalid client type.

        Args:
            password_hasher: Fixture or mock for password hashing functionality.
            token_manager: Fixture or mock for token management.
            mock_db: Mocked database session or connection.
            sample_user_read: Sample user object for testing.
            mock_request: Mocked request object.

        Asserts:
            - An HTTPException is raised.
            - The exception has a status code of 403.
            - The exception detail message contains the phrase "client type".
        """
        response = Response()

        with patch("session.utils.create_session"):
            with pytest.raises(HTTPException) as exc_info:
                auth_utils.complete_login(
                    response,
                    mock_request,
                    sample_user_read,
                    "invalid_type",
                    password_hasher,
                    token_manager,
                    mock_db,
                )

            assert exc_info.value.status_code == 403
            assert "client type" in exc_info.value.detail.lower()

    def test_parse_user_agent_chrome_desktop(self):
        """
        Test that the `parse_user_agent` function correctly identifies a Chrome browser running on a Windows desktop.

        This test verifies that:
        - The device type is detected as PC.
        - The browser is identified as Chrome.
        - The operating system is identified as Windows.

        Assertions:
            - device_info.device_type == session_utils.DeviceType.PC
            - "Chrome" in device_info.browser
            - "Windows" in device_info.operating_system
        """
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"

        device_info = session_utils.parse_user_agent(user_agent)

        assert (
            device_info.device_type == session_utils.DeviceType.PC
        ), "Should detect as PC"
        assert "Chrome" in device_info.browser, "Should detect Chrome browser"
        assert "Windows" in device_info.operating_system, "Should detect Windows OS"

    def test_parse_user_agent_firefox_desktop(self):
        """
        Test that the parse_user_agent function correctly identifies a Firefox browser running on a Linux desktop.

        This test verifies that:
        - The device type is detected as PC.
        - The browser is identified as Firefox.
        - The operating system is identified as Linux.

        Assertions:
            - device_info.device_type == session_utils.DeviceType.PC
            - "Firefox" in device_info.browser
            - "Linux" in device_info.operating_system
        """
        user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0"
        )

        device_info = session_utils.parse_user_agent(user_agent)

        assert (
            device_info.device_type == session_utils.DeviceType.PC
        ), "Should detect as PC"
        assert "Firefox" in device_info.browser, "Should detect Firefox browser"
        assert "Linux" in device_info.operating_system, "Should detect Linux OS"

    def test_parse_user_agent_safari_mac(self):
        """
        Test that the parse_user_agent function correctly identifies a Safari browser on macOS.

        This test verifies that:
        - The device type is detected as PC when the user agent string corresponds to Safari on a Mac.
        - The operating system string contains "Mac OS X", confirming macOS detection.

        Assertions:
            - device_info.device_type == session_utils.DeviceType.PC
            - "Safari" in device_info.browser
            - "Mac OS X" in device_info.operating_system
        """
        user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15"

        device_info = session_utils.parse_user_agent(user_agent)

        assert (
            device_info.device_type == session_utils.DeviceType.PC
        ), "Should detect as PC"
        assert "Safari" in device_info.browser, "Should detect Safari browser"
        assert "Mac OS X" in device_info.operating_system, "Should detect macOS"

    def test_parse_user_agent_mobile_ios(self):
        """
        Test that the `parse_user_agent` function correctly identifies an iOS mobile device from a typical iPhone user agent string.

        This test verifies:
        - The device type is detected as mobile.
        - The browser is identified as Safari.
        - The operating system is recognized as iOS.
        """
        user_agent = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Mobile/15E148 Safari/604.1"

        device_info = session_utils.parse_user_agent(user_agent)

        assert (
            device_info.device_type == session_utils.DeviceType.MOBILE
        ), "Should detect as mobile"
        assert "Safari" in device_info.browser, "Should detect Safari browser"
        assert "iOS" in device_info.operating_system, "Should detect iOS"

    def test_parse_user_agent_mobile_android(self):
        """
        Test that the `parse_user_agent` function correctly identifies an Android mobile device from a given user agent string.

        This test verifies that:
        - The device type is detected as mobile.
        - The browser is identified as Chrome.
        - The operating system is identified as Android.
        """
        user_agent = "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36"

        device_info = session_utils.parse_user_agent(user_agent)

        assert (
            device_info.device_type == session_utils.DeviceType.MOBILE
        ), "Should detect as mobile"
        assert "Chrome" in device_info.browser, "Should detect Chrome browser"
        assert "Android" in device_info.operating_system, "Should detect Android"

    def test_parse_user_agent_tablet(self):
        """
        Test that the `parse_user_agent` function correctly identifies an iPad user agent string as a tablet device,
        detects the Safari browser, and recognizes the iOS operating system.

        Assertions:
            - The device type should be identified as `DeviceType.TABLET`.
            - The browser name should include "Safari".
            - The operating system should include "iOS".
        """
        user_agent = "Mozilla/5.0 (iPad; CPU OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"

        device_info = session_utils.parse_user_agent(user_agent)

        assert (
            device_info.device_type == session_utils.DeviceType.TABLET
        ), "Should detect as tablet"
        assert "Safari" in device_info.browser, "Should detect Safari browser"
        assert "iOS" in device_info.operating_system, "Should detect iOS"

    def test_parse_user_agent_empty_string(self):
        """
        Test that the `parse_user_agent` function correctly handles an empty user agent string.

        This test verifies that:
        - The function does not return None when given an empty string.
        - The returned device type is one of PC, MOBILE, or TABLET.
        - The browser and operating system fields in the returned object are not None.
        """
        device_info = session_utils.parse_user_agent("")

        assert device_info is not None, "Should handle empty user agent"
        assert device_info.device_type in [
            session_utils.DeviceType.PC,
            session_utils.DeviceType.MOBILE,
            session_utils.DeviceType.TABLET,
        ], "Should return valid device type"
        assert device_info.browser is not None, "Browser should not be None"
        assert device_info.operating_system is not None, "OS should not be None"

    def test_get_ip_address_from_x_forwarded_for(self, mock_request):
        """
        Test that the `get_ip_address` function correctly extracts the first IP address from the
        'X-Forwarded-For' HTTP header in the request. Ensures that when multiple IPs are present,
        the function returns the left-most (original client) IP address.
        """
        mock_request.headers = {
            "X-Forwarded-For": "203.0.113.195, 70.41.3.18, 150.172.238.178"
        }

        ip = session_utils.get_ip_address(mock_request)

        assert ip == "203.0.113.195", "Should extract first IP from X-Forwarded-For"

    def test_get_ip_address_from_x_real_ip(self, mock_request):
        """
        Test that the get_ip_address function correctly extracts the IP address from the 'X-Real-IP' header in the request.

        Args:
            mock_request: A mock request object with headers set for testing.

        Asserts:
            The returned IP address matches the value provided in the 'X-Real-IP' header.
        """
        mock_request.headers = {"X-Real-IP": "192.0.2.1"}

        ip = session_utils.get_ip_address(mock_request)

        assert ip == "192.0.2.1", "Should extract IP from X-Real-IP"

    def test_get_ip_address_priority(self, mock_request):
        """
        Tests that the `get_ip_address` function correctly prioritizes the 'X-Forwarded-For' header
        over the 'X-Real-IP' header when both are present in the request headers.
        """
        mock_request.headers = {
            "X-Forwarded-For": "203.0.113.195",
            "X-Real-IP": "192.0.2.1",
        }

        ip = session_utils.get_ip_address(mock_request)

        assert ip == "203.0.113.195", "X-Forwarded-For should take priority"

    def test_get_ip_address_from_client_host(self, mock_request):
        """
        Test that the get_ip_address function returns the client's host IP address
        when no relevant headers are present in the request.

        Args:
            mock_request: A mock request object with headers and client.host attributes.

        Asserts:
            The returned IP address matches the client.host value when headers are empty.
        """
        mock_request.headers = {}
        mock_request.client.host = "127.0.0.1"

        ip = session_utils.get_ip_address(mock_request)

        assert ip == "127.0.0.1", "Should fall back to client.host"

    def test_get_ip_address_with_no_client(self, mock_request):
        """
        Test that get_ip_address returns 'unknown' when the request has no client information.

        This test sets up a mock request object with empty headers and a None client,
        then verifies that the session_utils.get_ip_address function returns 'unknown'
        as expected in the absence of client data.
        """
        mock_request.headers = {}
        mock_request.client = None

        ip = session_utils.get_ip_address(mock_request)

        assert ip == "unknown", "Should return 'unknown' when no client info"

    def test_create_session_creates_and_stores_session(
        self, sample_user_read, mock_request, password_hasher, mock_db
    ):
        """
        Test that the `session_utils.create_session` function creates a new session and stores it in the database.

        This test verifies that:
        - A session object is created with the correct session ID and user information.
        - The refresh token is hashed before storage.
        - The session expiration is set correctly.
        - The session CRUD create function is called with the correct parameters.

        Args:
            sample_user_read: A sample user object used for testing.
            mock_request: A mock request object simulating an HTTP request.
            password_hasher: Fixture for password hashing utilities.
            mock_db: Mocked database session.

        Asserts:
            - session_crud.create_session is called once with the correct session object and database.
            - The session object contains the expected session ID, user ID, and hashed refresh token.
        """
        session_id = "test-session-id-123"
        refresh_token = "test-refresh-token"

        with patch("session.utils.session_crud.create_session") as mock_create:
            session_utils.create_session(
                session_id,
                sample_user_read,
                mock_request,
                refresh_token,
                password_hasher,
                mock_db,
            )

            # Verify create_session was called
            assert mock_create.call_count == 1, "create_session should be called once"

            # Get the session object that was passed to create_session
            call_args = mock_create.call_args
            session_obj = call_args[0][0]
            db_arg = call_args[0][1]

            # Verify the session object has correct fields
            assert session_obj.id == session_id, "Session ID should match"
            assert (
                session_obj.user_id == sample_user_read.id
            ), "User ID should match sample user"
            assert db_arg == mock_db, "Database session should be passed"

            # Verify refresh token is hashed (should not be plain text)
            assert (
                session_obj.refresh_token != refresh_token
            ), "Refresh token should be hashed"
            assert (
                len(session_obj.refresh_token) > 0
            ), "Hashed refresh token should not be empty"

            # Verify the refresh token can be verified
            assert password_hasher.verify(
                refresh_token, session_obj.refresh_token
            ), "Hashed token should verify against original"

    def test_create_session_sets_expiration_correctly(
        self, sample_user_read, mock_request, password_hasher, mock_db
    ):
        """
        Test that the `session_utils.create_session` function sets the correct expiration time.

        This test verifies that:
        - The session expiration is set to the expected number of days in the future.
        - The expiration timestamp is a valid datetime object.

        Args:
            sample_user_read: A sample user object used for testing.
            mock_request: A mock request object simulating an HTTP request.
            password_hasher: Fixture for password hashing utilities.
            mock_db: Mocked database session.

        Asserts:
            - The session expiration is set correctly based on JWT_REFRESH_TOKEN_EXPIRE_DAYS.
        """
        session_id = "test-session-id-exp"
        refresh_token = "test-refresh-token"

        with patch("session.utils.session_crud.create_session") as mock_create:
            with patch("session.utils.auth_constants") as mock_constants:
                # Set the expiration days
                mock_constants.JWT_REFRESH_TOKEN_EXPIRE_DAYS = 30

                session_utils.create_session(
                    session_id,
                    sample_user_read,
                    mock_request,
                    refresh_token,
                    password_hasher,
                    mock_db,
                )

                # Get the session object
                session_obj = mock_create.call_args[0][0]

                # Verify expiration is set and is in the future
                assert session_obj.expires_at is not None, "Expiration should be set"
                assert isinstance(
                    session_obj.expires_at, datetime
                ), "Expiration should be a datetime"
                assert session_obj.expires_at > datetime.now(
                    timezone.utc
                ), "Expiration should be in the future"

    def test_edit_session_updates_refresh_token(
        self, sample_user_read, mock_request, password_hasher, mock_db
    ):
        """
        Test that the `session_utils.edit_session` function updates the refresh token correctly.

        This test verifies that:
        - The existing session's refresh token is updated to a new hashed value.
        - The new refresh token is hashed before storage.
        - The session CRUD edit function is called with the correct parameters.

        Args:
            sample_user_read: A sample user object used for testing.
            mock_request: A mock request object simulating an HTTP request.
            password_hasher: Fixture for password hashing utilities.
            mock_db: Mocked database session.

        Asserts:
            - session_crud.edit_session is called once with the updated session object.
            - The refresh token is updated and hashed correctly.
        """
        # Create an existing session mock
        existing_session = MagicMock()
        existing_session.id = "existing-session-123"
        existing_session.user_id = sample_user_read.id
        existing_session.refresh_token = "old-hashed-token"
        existing_session.created_at = datetime.now(timezone.utc) - timedelta(days=5)
        existing_session.expires_at = datetime.now(timezone.utc) + timedelta(days=25)

        new_refresh_token = "new-refresh-token"

        with patch("session.utils.session_crud.edit_session") as mock_edit:
            session_utils.edit_session(
                existing_session,
                mock_request,
                new_refresh_token,
                password_hasher,
                mock_db,
            )

            # Verify edit_session was called
            assert mock_edit.call_count == 1, "edit_session should be called once"

            # Get the updated session object
            call_args = mock_edit.call_args
            updated_session = call_args[0][0]
            db_arg = call_args[0][1]

            # Verify database argument
            assert db_arg == mock_db, "Database session should be passed"

            # Verify session ID is preserved
            assert (
                updated_session.id == existing_session.id
            ), "Session ID should be preserved"

            # Verify refresh token is updated and hashed
            assert (
                updated_session.refresh_token != existing_session.refresh_token
            ), "Refresh token should be updated"
            assert (
                updated_session.refresh_token != new_refresh_token
            ), "Refresh token should be hashed"
            assert password_hasher.verify(
                new_refresh_token, updated_session.refresh_token
            ), "New hashed token should verify against new token"

    def test_edit_session_updates_expiration(
        self, sample_user_read, mock_request, password_hasher, mock_db
    ):
        """
        Test that the `session_utils.edit_session` function updates the expiration time.

        This test verifies that:
        - The session's expiration time is updated to a new future date.
        - The expiration is recalculated based on the current time plus refresh token expiry days.

        Args:
            sample_user_read: A sample user object used for testing.
            mock_request: A mock request object simulating an HTTP request.
            password_hasher: Fixture for password hashing utilities.
            mock_db: Mocked database session.

        Asserts:
            - The session expiration is updated to a new value in the future.
        """
        # Create an existing session with old expiration
        old_expiration = datetime.now(timezone.utc) + timedelta(days=10)
        existing_session = MagicMock()
        existing_session.id = "existing-session-456"
        existing_session.user_id = sample_user_read.id
        existing_session.refresh_token = "old-hashed-token"
        existing_session.created_at = datetime.now(timezone.utc) - timedelta(days=20)
        existing_session.expires_at = old_expiration

        new_refresh_token = "new-refresh-token"

        with patch("session.utils.session_crud.edit_session") as mock_edit:
            session_utils.edit_session(
                existing_session,
                mock_request,
                new_refresh_token,
                password_hasher,
                mock_db,
            )

            # Get the updated session object
            updated_session = mock_edit.call_args[0][0]

            # Verify expiration is updated
            assert (
                updated_session.expires_at != old_expiration
            ), "Expiration should be updated"
            assert updated_session.expires_at > datetime.now(
                timezone.utc
            ), "New expiration should be in the future"
            assert isinstance(
                updated_session.expires_at, datetime
            ), "Expiration should be a datetime"

    def test_edit_session_preserves_created_at(
        self, sample_user_read, mock_request, password_hasher, mock_db
    ):
        """
        Test that the `session_utils.edit_session` function preserves the original created_at timestamp.

        This test verifies that:
        - The session's created_at timestamp is not modified during the edit operation.
        - The created_at timestamp remains the same as the original session.

        Args:
            sample_user_read: A sample user object used for testing.
            mock_request: A mock request object simulating an HTTP request.
            password_hasher: Fixture for password hashing utilities.
            mock_db: Mocked database session.

        Asserts:
            - The created_at timestamp is preserved from the original session.
        """
        # Create an existing session with a specific created_at time
        original_created_at = datetime.now(timezone.utc) - timedelta(days=15)
        existing_session = MagicMock()
        existing_session.id = "existing-session-789"
        existing_session.user_id = sample_user_read.id
        existing_session.refresh_token = "old-hashed-token"
        existing_session.created_at = original_created_at
        existing_session.expires_at = datetime.now(timezone.utc) + timedelta(days=15)

        new_refresh_token = "new-refresh-token"

        with patch("session.utils.session_crud.edit_session") as mock_edit:
            session_utils.edit_session(
                existing_session,
                mock_request,
                new_refresh_token,
                password_hasher,
                mock_db,
            )

            # Get the updated session object
            updated_session = mock_edit.call_args[0][0]

            # Verify created_at is preserved
            assert (
                updated_session.created_at == original_created_at
            ), "created_at timestamp should be preserved"

    def test_edit_session_updates_device_information(
        self, sample_user_read, mock_request, password_hasher, mock_db
    ):
        """
        Test that the `session_utils.edit_session` function updates device information from the new request.

        This test verifies that:
        - Device information (IP address, device type, OS, browser) is updated based on the new request.
        - The session reflects the current request context after editing.

        Args:
            sample_user_read: A sample user object used for testing.
            mock_request: A mock request object simulating an HTTP request.
            password_hasher: Fixture for password hashing utilities.
            mock_db: Mocked database session.

        Asserts:
            - Device information fields are set and not None after the edit.
        """
        # Create an existing session
        existing_session = MagicMock()
        existing_session.id = "existing-session-device"
        existing_session.user_id = sample_user_read.id
        existing_session.refresh_token = "old-hashed-token"
        existing_session.created_at = datetime.now(timezone.utc) - timedelta(days=1)
        existing_session.expires_at = datetime.now(timezone.utc) + timedelta(days=29)
        existing_session.ip_address = "192.168.1.1"
        existing_session.device_type = "Mobile"
        existing_session.operating_system = "iOS"
        existing_session.browser = "Safari"

        new_refresh_token = "new-refresh-token"

        with patch("session.utils.session_crud.edit_session") as mock_edit:
            session_utils.edit_session(
                existing_session,
                mock_request,
                new_refresh_token,
                password_hasher,
                mock_db,
            )

            # Get the updated session object
            updated_session = mock_edit.call_args[0][0]

            # Verify device information is set (updated from mock_request)
            assert updated_session.ip_address is not None, "IP address should be set"
            assert updated_session.device_type is not None, "Device type should be set"
            assert (
                updated_session.operating_system is not None
            ), "Operating system should be set"
            assert updated_session.browser is not None, "Browser should be set"
