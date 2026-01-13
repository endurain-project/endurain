"""Tests for user_identity_providers.utils module."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from users.user_identity_providers import utils as user_idp_utils
from users.user_identity_providers.schema import UserIdentityProviderResponse


class TestEnrichUserIdentityProviders:
    """Test suite for enrich_user_identity_providers function."""

    def test_enrich_user_identity_providers_empty_list(self, mock_db):
        """Test enriching empty IdP links list.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns empty list immediately
            - No database queries executed
        """
        # Arrange
        idp_links = []

        # Act
        result = user_idp_utils.enrich_user_identity_providers(idp_links, 1, mock_db)

        # Assert
        assert result == []
        mock_db.execute.assert_not_called()

    def test_enrich_user_identity_providers_success(self, mock_db):
        """Test enriching user identity provider links.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns list of enriched responses
            - All IdP details are included
            - Batch fetching is used
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Mock IdP links
        mock_link1 = MagicMock()
        mock_link1.id = 1
        mock_link1.user_id = 1
        mock_link1.idp_id = 1
        mock_link1.idp_subject = "user123@strava.com"
        mock_link1.linked_at = now
        mock_link1.last_login = now

        mock_link2 = MagicMock()
        mock_link2.id = 2
        mock_link2.user_id = 1
        mock_link2.idp_id = 2
        mock_link2.idp_subject = "user456@garmin.com"
        mock_link2.linked_at = now
        mock_link2.last_login = now

        # Mock IdPs
        mock_idp1 = MagicMock()
        mock_idp1.id = 1
        mock_idp1.name = "Strava"
        mock_idp1.slug = "strava"
        mock_idp1.icon = "https://example.com/strava.svg"
        mock_idp1.provider_type = "oauth2"

        mock_idp2 = MagicMock()
        mock_idp2.id = 2
        mock_idp2.name = "Garmin"
        mock_idp2.slug = "garmin"
        mock_idp2.icon = "https://example.com/garmin.svg"
        mock_idp2.provider_type = "oauth2"

        with patch(
            "users.user_identity_providers.utils.idp_crud"
            ".get_identity_providers_by_ids"
        ) as mock_get_idps:
            mock_get_idps.return_value = [mock_idp1, mock_idp2]

            # Act
            result = user_idp_utils.enrich_user_identity_providers(
                [mock_link1, mock_link2], 1, mock_db
            )

        # Assert
        assert len(result) == 2
        assert result[0].idp_name == "Strava"
        assert result[0].idp_slug == "strava"
        assert result[1].idp_name == "Garmin"
        assert result[1].idp_slug == "garmin"
        mock_get_idps.assert_called_once()

    def test_enrich_user_identity_providers_partial_results(self, mock_db):
        """Test enriching when some IdPs are missing.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns only enriched links for existing IdPs
            - Missing IdPs are skipped
            - Warning is logged
        """
        # Arrange
        now = datetime.now(timezone.utc)

        # Mock IdP links - 2 links
        mock_link1 = MagicMock()
        mock_link1.id = 1
        mock_link1.user_id = 1
        mock_link1.idp_id = 1
        mock_link1.idp_subject = "user@example.com"
        mock_link1.linked_at = now

        mock_link2 = MagicMock()
        mock_link2.id = 2
        mock_link2.user_id = 1
        mock_link2.idp_id = 2
        mock_link2.idp_subject = "user@example.com"
        mock_link2.linked_at = now

        # Mock IdPs - only 1 exists
        mock_idp1 = MagicMock()
        mock_idp1.id = 1
        mock_idp1.name = "Strava"
        mock_idp1.slug = "strava"
        mock_idp1.icon = "icon"
        mock_idp1.provider_type = "oauth2"

        with patch(
            "users.user_identity_providers.utils.idp_crud"
            ".get_identity_providers_by_ids"
        ) as mock_get_idps:
            with patch(
                "users.user_identity_providers.utils.core_logger.print_to_log"
            ) as mock_logger:
                mock_get_idps.return_value = [mock_idp1]

                # Act
                result = user_idp_utils.enrich_user_identity_providers(
                    [mock_link1, mock_link2], 1, mock_db
                )

        # Assert
        assert len(result) == 1
        assert result[0].idp_name == "Strava"
        mock_logger.assert_called_once()  # Warning logged for missing IdP

    def test_enrich_user_identity_providers_no_results(self, mock_db):
        """Test enriching when no IdPs are found.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns empty list when no IdPs match
            - Warnings logged for all missing IdPs
        """
        # Arrange
        now = datetime.now(timezone.utc)

        mock_link = MagicMock()
        mock_link.id = 1
        mock_link.idp_id = 1
        mock_link.linked_at = now

        with patch(
            "users.user_identity_providers.utils.idp_crud"
            ".get_identity_providers_by_ids"
        ) as mock_get_idps:
            with patch(
                "users.user_identity_providers.utils.core_logger.print_to_log"
            ) as mock_logger:
                mock_get_idps.return_value = []

                # Act
                result = user_idp_utils.enrich_user_identity_providers(
                    [mock_link], 1, mock_db
                )

        # Assert
        assert result == []
        mock_logger.assert_called_once()


class TestGetUserIdentityProviderRefreshTokenByUserIdAndIdpId:
    """Test suite for get_user_identity_provider_refresh_token_by_user_id_and_idp_id."""

    def test_get_refresh_token_success(self, mock_db):
        """Test retrieving refresh token.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns refresh token when link exists
            - Returns None when token is not set
        """
        # Arrange
        with patch(
            "users.user_identity_providers.utils.user_idp_crud"
            ".get_user_identity_provider_by_user_id_and_idp_id"
        ) as mock_get:
            mock_link = MagicMock()
            mock_link.idp_refresh_token = "encrypted_token_xyz"
            mock_get.return_value = mock_link

            # Act
            result = user_idp_utils.get_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                1, 1, mock_db
            )

        # Assert
        assert result == "encrypted_token_xyz"

    def test_get_refresh_token_not_found(self, mock_db):
        """Test retrieving token when link doesn't exist.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns None when link not found
        """
        # Arrange
        with patch(
            "users.user_identity_providers.utils.user_idp_crud"
            ".get_user_identity_provider_by_user_id_and_idp_id"
        ) as mock_get:
            mock_get.return_value = None

            # Act
            result = user_idp_utils.get_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                1, 1, mock_db
            )

        # Assert
        assert result is None

    def test_get_refresh_token_none_value(self, mock_db):
        """Test retrieving when token value is None.

        Args:
            mock_db: Mocked database session

        Asserts:
            - Returns None when token is not set
        """
        # Arrange
        with patch(
            "users.user_identity_providers.utils.user_idp_crud"
            ".get_user_identity_provider_by_user_id_and_idp_id"
        ) as mock_get:
            mock_link = MagicMock()
            mock_link.idp_refresh_token = None
            mock_get.return_value = mock_link

            # Act
            result = user_idp_utils.get_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                1, 1, mock_db
            )

        # Assert
        assert result is None
