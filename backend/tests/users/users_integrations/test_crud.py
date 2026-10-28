"""Tests for user_integrations.crud module."""

from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
from modules.users.users_integrations import crud as user_integrations_crud
from modules.users.users_integrations.models import UsersIntegrations


@pytest.fixture(autouse=True)
def _patch_transform():
    """Patch _transform_users_integrations to a passthrough for MagicMock compatibility."""
    with patch(
        "modules.users.users_integrations.crud.user_integrations_serializers.to_read_schema",
        side_effect=lambda x: x,
    ):
        yield


class TestGetUserIntegrationsByUserId:
    """Test suite for get_user_integrations_by_user_id function."""

    def test_get_user_integrations_by_user_id_success(self, mock_db):
        """Test retrieving integrations for a user.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns UsersIntegrations object when found
            - Database query is executed correctly
        """
        # Arrange
        mock_integrations = MagicMock(spec=UsersIntegrations)
        mock_integrations.id = 1
        mock_integrations.user_id = 1
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_integrations

        # Act
        result = user_integrations_crud.get_user_integrations_by_user_id(1, mock_db)

        # Assert
        assert result == mock_integrations
        mock_db.execute.assert_called_once()

    def test_get_user_integrations_by_user_id_not_found(self, mock_db):
        """Test retrieving integrations when not found.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns None when integrations not found
        """
        # Arrange
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # Act
        result = user_integrations_crud.get_user_integrations_by_user_id(1, mock_db)

        # Assert
        assert result is None


class TestCreateUserIntegrations:
    """Test suite for create_user_integrations function."""

    def test_create_user_integrations_success(self, mock_db):
        """Test creating user integrations.

        Args:
            mock_db: Mocked database session

        Asserts:
            - New integrations record is created
            - Database operations are called correctly
        """
        # Arrange
        mock_integrations = MagicMock(spec=UsersIntegrations)
        mock_integrations.id = 1
        mock_integrations.user_id = 1

        with patch(
            "modules.users.users_integrations.crud.user_integrations_models.UsersIntegrations"
        ) as mock_constructor:
            mock_constructor.return_value = mock_integrations
            mock_db.add = MagicMock()
            mock_db.flush = MagicMock()
            mock_db.refresh = MagicMock()

            # Act
            result = user_integrations_crud.create_user_integrations(1, mock_db)

        # Assert
        assert result == mock_integrations
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

    def test_create_user_integrations_conflict(self, mock_db):
        """Test creating integrations when already exist.

        Args:
            mock_db: Mocked database session

        Asserts:
            - ConflictError on IntegrityError
        """
        # Arrange
        mock_db.add.side_effect = IntegrityError("", "", "duplicate key")

        # Act & Assert
        with pytest.raises(core_exceptions.ConflictError):
            user_integrations_crud.create_user_integrations(1, mock_db)


class TestLinkStravaAccount:
    """Test suite for link_strava_account function."""

    def test_link_strava_account_success(self, mock_db):
        """Test linking a Strava account.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Strava tokens are stored
            - Database operations are called
        """
        # Arrange
        mock_integrations = MagicMock(spec=UsersIntegrations)
        tokens = {
            "access_token": "access_token_123",
            "refresh_token": "refresh_token_456",
            "expires_at": 1234567890,
        }

        with (
            patch("modules.users.users_integrations.crud._get_user_integrations_model_by_user_id_or_404") as mock_get,
            patch("modules.users.users_integrations.crud.core_cryptography.encrypt_token_fernet") as mock_encrypt,
        ):
            mock_get.return_value = mock_integrations
            mock_encrypt.side_effect = lambda x: f"encrypted_{x}"
            mock_db.flush = MagicMock()
            mock_db.refresh = MagicMock()

            # Act
            user_integrations_crud.link_strava_account(1, tokens, mock_db)

        # Assert
        assert mock_integrations.strava_token == "encrypted_access_token_123"
        assert mock_integrations.strava_refresh_token == "encrypted_refresh_token_456"
        mock_db.flush.assert_called_once()


class TestUnlinkStravaAccount:
    """Test suite for unlink_strava_account function."""

    def test_unlink_strava_account_success(self, mock_db):
        """
        ...
        """
        # Arrange
        mock_integrations = MagicMock(spec=UsersIntegrations)

        with patch("modules.users.users_integrations.crud._get_user_integrations_model_by_user_id_or_404") as mock_get:
            mock_get.return_value = mock_integrations
            mock_db.flush = MagicMock()
            mock_db.refresh = MagicMock()

            # Act
            user_integrations_crud.unlink_strava_account(1, mock_db)

        # Assert
        assert mock_integrations.strava_token is None
        assert mock_integrations.strava_refresh_token is None
        assert mock_integrations.strava_token_expires_at is None
        assert mock_integrations.strava_sync_gear is False
        assert mock_integrations.strava_client_id is None
        assert mock_integrations.strava_client_secret is None
        mock_db.flush.assert_called_once()

    def test_unlink_strava_account_not_found(self, mock_db):
        """Test unlinking when integrations not found."""
        # Arrange
        with patch("modules.users.users_integrations.crud._get_user_integrations_model_by_user_id_or_404") as mock_get:
            mock_get.side_effect = core_exceptions.NotFoundError("not found")

            # Act & Assert
            with pytest.raises(core_exceptions.NotFoundError):
                user_integrations_crud.unlink_strava_account(1, mock_db)


class TestSetUserStravaClient:
    """Test suite for set_user_strava_client function."""

    def test_set_user_strava_client_success(self, mock_db):
        """
        ...
        """
        # Arrange
        mock_integrations = MagicMock(spec=UsersIntegrations)

        with (
            patch("modules.users.users_integrations.crud._get_user_integrations_model_by_user_id_or_404") as mock_get,
            patch("modules.users.users_integrations.crud.core_cryptography.encrypt_token_fernet") as mock_encrypt,
        ):
            mock_get.return_value = mock_integrations
            mock_encrypt.side_effect = lambda x: f"encrypted_{x}"
            mock_db.flush = MagicMock()
            mock_db.refresh = MagicMock()

            # Act
            user_integrations_crud.set_user_strava_client(1, "client_id", "client_secret", mock_db, if_match="*")

        # Assert
        assert mock_integrations.strava_client_id == "encrypted_client_id"
        assert mock_integrations.strava_client_secret == "encrypted_client_secret"
        mock_db.flush.assert_called_once()

    def test_a_stale_version_is_refused(self, mock_db):
        mock_integrations = MagicMock(spec=UsersIntegrations)
        mock_integrations.version = 4

        with (
            patch(
                "modules.users.users_integrations.crud._get_user_integrations_model_by_user_id_or_404",
                return_value=mock_integrations,
            ),
            pytest.raises(core_exceptions.PreconditionFailedError),
        ):
            user_integrations_crud.set_user_strava_client(1, "id", "secret", mock_db, if_match='"3"')

        mock_db.flush.assert_not_called()

    def test_set_user_strava_client_not_found(self, mock_db):
        """Test setting client when integrations not found."""
        # Arrange
        with patch("modules.users.users_integrations.crud._get_user_integrations_model_by_user_id_or_404") as mock_get:
            mock_get.side_effect = core_exceptions.NotFoundError("not found")

            # Act & Assert
            with pytest.raises(core_exceptions.NotFoundError):
                user_integrations_crud.set_user_strava_client(1, "id", "secret", mock_db, if_match="*")


class TestSetUserStravaSyncGear:
    """Test suite for set_user_strava_sync_gear function."""

    def test_set_user_strava_sync_gear_true(self, mock_db):
        """
        ...
        """
        # Arrange
        mock_integrations = MagicMock(spec=UsersIntegrations)

        with patch("modules.users.users_integrations.crud._get_user_integrations_model_by_user_id_or_404") as mock_get:
            mock_get.return_value = mock_integrations
            mock_db.flush = MagicMock()

            # Act
            user_integrations_crud.set_user_strava_sync_gear(1, True, mock_db)

        # Assert
        assert mock_integrations.strava_sync_gear is True

    def test_set_user_strava_sync_gear_false(self, mock_db):
        """
        ...
        """
        # Arrange
        mock_integrations = MagicMock(spec=UsersIntegrations)

        with patch("modules.users.users_integrations.crud._get_user_integrations_model_by_user_id_or_404") as mock_get:
            mock_get.return_value = mock_integrations
            mock_db.flush = MagicMock()

            # Act
            user_integrations_crud.set_user_strava_sync_gear(1, False, mock_db)

        # Assert
        assert mock_integrations.strava_sync_gear is False


class TestLinkGarminConnectAccount:
    """Test suite for link_garminconnect_account function."""

    def test_link_garminconnect_account_success(self, mock_db):
        """
        ...
        """
        # Arrange
        mock_integrations = MagicMock(spec=UsersIntegrations)
        token = {"token": "garmin_token"}

        with patch("modules.users.users_integrations.crud._get_user_integrations_model_by_user_id_or_404") as mock_get:
            mock_get.return_value = mock_integrations
            mock_db.flush = MagicMock()

            # Act
            user_integrations_crud.link_garminconnect_account(1, token, mock_db)

        # Assert
        assert mock_integrations.garminconnect_token == token
        mock_db.flush.assert_not_called()

    def test_link_garminconnect_account_not_found(self, mock_db):
        """Test linking when integrations not found."""
        # Arrange
        with patch("modules.users.users_integrations.crud._get_user_integrations_model_by_user_id_or_404") as mock_get:
            mock_get.side_effect = core_exceptions.NotFoundError("not found")

            # Act & Assert
            with pytest.raises(core_exceptions.NotFoundError):
                user_integrations_crud.link_garminconnect_account(1, {}, mock_db)


class TestSetUserGarminConnectSyncGear:
    """Test suite for set_user_garminconnect_sync_gear function."""

    def test_set_user_garminconnect_sync_gear_true(self, mock_db):
        """
        ...
        """
        # Arrange
        mock_integrations = MagicMock(spec=UsersIntegrations)

        with patch("modules.users.users_integrations.crud._get_user_integrations_model_by_user_id_or_404") as mock_get:
            mock_get.return_value = mock_integrations
            mock_db.flush = MagicMock()

            # Act
            user_integrations_crud.set_user_garminconnect_sync_gear(1, True, mock_db)

        # Assert
        assert mock_integrations.garminconnect_sync_gear is True

    def test_set_user_garminconnect_sync_gear_false(self, mock_db):
        """
        ...
        """
        # Arrange
        mock_integrations = MagicMock(spec=UsersIntegrations)

        with patch("modules.users.users_integrations.crud._get_user_integrations_model_by_user_id_or_404") as mock_get:
            mock_get.return_value = mock_integrations
            mock_db.flush = MagicMock()

            # Act
            user_integrations_crud.set_user_garminconnect_sync_gear(1, False, mock_db)

        # Assert
        assert mock_integrations.garminconnect_sync_gear is False


class TestUnlinkGarminConnectAccount:
    """Test suite for unlink_garminconnect_account function."""

    def test_unlink_garminconnect_account_success(self, mock_db):
        """
        ...
        """
        # Arrange
        mock_integrations = MagicMock(spec=UsersIntegrations)

        with patch("modules.users.users_integrations.crud._get_user_integrations_model_by_user_id_or_404") as mock_get:
            mock_get.return_value = mock_integrations
            mock_db.flush = MagicMock()

            # Act
            user_integrations_crud.unlink_garminconnect_account(1, mock_db)

        # Assert
        assert mock_integrations.garminconnect_token is None
        assert mock_integrations.garminconnect_sync_gear is False
        mock_db.flush.assert_not_called()

    def test_unlink_garminconnect_account_not_found(self, mock_db):
        """Test unlinking when integrations not found."""
        # Arrange
        with patch("modules.users.users_integrations.crud._get_user_integrations_model_by_user_id_or_404") as mock_get:
            mock_get.side_effect = core_exceptions.NotFoundError("not found")

            # Act & Assert
            with pytest.raises(core_exceptions.NotFoundError):
                user_integrations_crud.unlink_garminconnect_account(1, mock_db)


class TestUnlinkGarminConnectAccountIfToken:
    """Test suite for unlink_garminconnect_account_if_token function."""

    def test_unlinks_while_the_stored_token_is_the_rejected_one(self, mock_db):
        """The account is cleared, without committing, when the token is unchanged."""
        mock_integrations = MagicMock(spec=UsersIntegrations)
        mock_integrations.garminconnect_token = {"di_token": "old"}
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_integrations

        result = user_integrations_crud.unlink_garminconnect_account_if_token(1, {"di_token": "old"}, mock_db)

        assert result is True
        assert mock_integrations.garminconnect_token is None
        assert mock_integrations.garminconnect_sync_gear is False
        mock_db.flush.assert_not_called()

    def test_keeps_a_token_linked_since(self, mock_db):
        """A token replaced by a new link is left alone."""
        mock_integrations = MagicMock(spec=UsersIntegrations)
        mock_integrations.garminconnect_token = {"di_token": "new"}
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_integrations

        result = user_integrations_crud.unlink_garminconnect_account_if_token(1, {"di_token": "old"}, mock_db)

        assert result is False
        assert mock_integrations.garminconnect_token == {"di_token": "new"}

    def test_returns_false_without_integrations(self, mock_db):
        """A user with no integrations row is not unlinked."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        assert user_integrations_crud.unlink_garminconnect_account_if_token(1, {}, mock_db) is False


class TestReplaceStravaTokensIfRefreshToken:
    """Test suite for replace_strava_tokens_if_refresh_token function."""

    TOKENS: ClassVar[dict] = {"access_token": "a2", "refresh_token": "r2", "expires_at": 1234567890}

    def test_replaces_while_the_stored_refresh_token_is_the_one_refreshed_from(self, mock_db):
        """The new tokens are stored encrypted, without committing."""
        mock_integrations = MagicMock(spec=UsersIntegrations)
        mock_integrations.strava_refresh_token = "old"
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_integrations

        with patch("modules.users.users_integrations.crud.core_cryptography.encrypt_token_fernet") as encrypt:
            encrypt.side_effect = lambda value: f"enc_{value}"
            result = user_integrations_crud.replace_strava_tokens_if_refresh_token(1, "old", self.TOKENS, mock_db)

        assert result is True
        assert mock_integrations.strava_token == "enc_a2"
        assert mock_integrations.strava_refresh_token == "enc_r2"
        mock_db.commit.assert_not_called()

    def test_keeps_tokens_replaced_since(self, mock_db):
        """A refresh or a relink that got there first is not overwritten."""
        mock_integrations = MagicMock(spec=UsersIntegrations)
        mock_integrations.strava_refresh_token = "newer"
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_integrations

        result = user_integrations_crud.replace_strava_tokens_if_refresh_token(1, "old", self.TOKENS, mock_db)

        assert result is False
        assert mock_integrations.strava_refresh_token == "newer"

    def test_returns_false_without_integrations(self, mock_db):
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        assert user_integrations_crud.replace_strava_tokens_if_refresh_token(1, "old", self.TOKENS, mock_db) is False


class TestUnlinkStravaTokensIfRefreshToken:
    """Test suite for unlink_strava_tokens_if_refresh_token function."""

    def test_clears_the_tokens_and_keeps_the_client_while_the_refresh_token_is_the_rejected_one(self, mock_db):
        """The tokens are cleared, without committing; the client id and secret stay for a quick relink."""
        mock_integrations = MagicMock(spec=UsersIntegrations)
        mock_integrations.strava_refresh_token = "old"
        mock_integrations.strava_client_id = "client"
        mock_integrations.strava_client_secret = "secret"
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_integrations

        result = user_integrations_crud.unlink_strava_tokens_if_refresh_token(1, "old", mock_db)

        assert result is True
        assert mock_integrations.strava_token is None
        assert mock_integrations.strava_refresh_token is None
        assert mock_integrations.strava_token_expires_at is None
        assert mock_integrations.strava_sync_gear is False
        assert mock_integrations.strava_client_id == "client"
        assert mock_integrations.strava_client_secret == "secret"
        mock_db.flush.assert_not_called()

    def test_keeps_a_token_linked_since(self, mock_db):
        """A refresh token replaced by a new link or refresh is left alone."""
        mock_integrations = MagicMock(spec=UsersIntegrations)
        mock_integrations.strava_refresh_token = "new"
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_integrations

        result = user_integrations_crud.unlink_strava_tokens_if_refresh_token(1, "old", mock_db)

        assert result is False
        assert mock_integrations.strava_refresh_token == "new"

    def test_returns_false_without_integrations(self, mock_db):
        """A user with no integrations row is not unlinked."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        assert user_integrations_crud.unlink_strava_tokens_if_refresh_token(1, "old", mock_db) is False


class TestEditUserIntegrations:
    """Test suite for edit_user_integrations function."""

    def test_edit_user_integrations_success(self, mock_db):
        """
        ...
        """
        # Arrange
        mock_integrations = MagicMock(spec=UsersIntegrations)
        mock_update = MagicMock()
        mock_update.model_dump.return_value = {"strava_sync_gear": True}

        with patch("modules.users.users_integrations.crud._get_user_integrations_model_by_user_id_or_404") as mock_get:
            mock_get.return_value = mock_integrations
            mock_db.flush = MagicMock()
            mock_db.refresh = MagicMock()

            # Act
            result = user_integrations_crud.edit_user_integrations(mock_update, 1, mock_db)

        # Assert
        assert result == mock_integrations
        assert mock_integrations.strava_sync_gear is True
        mock_db.flush.assert_called_once()

    def test_edit_user_integrations_not_found(self, mock_db):
        """Test editing when integrations not found."""
        # Arrange
        mock_update = MagicMock()

        with patch("modules.users.users_integrations.crud._get_user_integrations_model_by_user_id_or_404") as mock_get:
            mock_get.side_effect = core_exceptions.NotFoundError("not found")

            # Act & Assert
            with pytest.raises(core_exceptions.NotFoundError):
                user_integrations_crud.edit_user_integrations(mock_update, 1, mock_db)


class TestReplaceGarminConnectTokenIfToken:
    """Test suite for replace_garminconnect_token_if_token function."""

    def test_replaces_while_the_stored_token_is_the_old_one(self, mock_db):
        """The refreshed token is stored, without committing."""
        mock_integrations = MagicMock(spec=UsersIntegrations)
        mock_integrations.garminconnect_token = {"di_token": "old"}
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_integrations

        result = user_integrations_crud.replace_garminconnect_token_if_token(
            1, {"di_token": "old"}, {"di_token": "new"}, mock_db
        )

        assert result is True
        assert mock_integrations.garminconnect_token == {"di_token": "new"}
        mock_db.flush.assert_not_called()

    def test_keeps_a_token_linked_since(self, mock_db):
        """A re-linked token is not overwritten by a refresh of the previous one."""
        mock_integrations = MagicMock(spec=UsersIntegrations)
        mock_integrations.garminconnect_token = {"di_token": "relinked"}
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_integrations

        result = user_integrations_crud.replace_garminconnect_token_if_token(
            1, {"di_token": "old"}, {"di_token": "new"}, mock_db
        )

        assert result is False
        assert mock_integrations.garminconnect_token == {"di_token": "relinked"}
