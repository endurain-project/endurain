"""Tests for auth.identity_provider_links.service module."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import modules.auth.identity_provider_links.integration_service as identity_links_integration
import modules.auth.identity_providers.integration_service as identity_links_utils
from modules.auth.identity_provider_links.schema import IdentityProviderLinkRead


class TestGetUserIdentityProviderRefreshToken:
    """Tests for get_user_identity_provider_refresh_token_by_user_id_and_idp_id."""

    def test_returns_refresh_token_when_link_exists(self, mock_db):
        """
        Returns encrypted refresh token from the link.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - Returns idp_refresh_token from the found link.
        """
        mock_link = MagicMock()
        mock_link.idp_refresh_token = "encrypted-token-abc"

        with patch(
            "modules.auth.identity_provider_links.service.identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id",
            return_value=mock_link,
        ):
            result = identity_links_integration.get_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                user_id=1,
                idp_id=2,
                db=mock_db,
            )

        assert result == "encrypted-token-abc"

    def test_returns_none_when_link_not_found(self, mock_db):
        """
        Returns None when no link exists for user + IdP.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - Returns None.
        """
        with patch(
            "modules.auth.identity_provider_links.service.identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id",
            return_value=None,
        ):
            result = identity_links_integration.get_user_identity_provider_refresh_token_by_user_id_and_idp_id(
                user_id=1,
                idp_id=2,
                db=mock_db,
            )

        assert result is None


class TestEnrichUserIdentityProviders:
    """Tests for enrich_user_identity_providers."""

    def test_returns_empty_list_for_empty_input(self, mock_db):
        """
        Returns empty list immediately without DB queries.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - Returns empty list.
            - No db.execute called.
        """
        result = identity_links_utils.enrich_user_identity_providers([], 1, mock_db)

        assert result == []
        mock_db.execute.assert_not_called()

    def test_enriches_links_with_idp_details(self, mock_db):
        """
        Enriches links with name, slug, icon, provider_type.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - Returns enriched IdentityProviderLinkRead list.
            - idp_crud called once for batch fetch.
        """
        now = datetime.now(UTC)

        mock_link = MagicMock()
        mock_link.id = 1
        mock_link.user_id = 1
        mock_link.idp_id = 1
        mock_link.idp_subject = "sub-123"
        mock_link.linked_at = now
        mock_link.last_login = now
        mock_link.idp_access_token_expires_at = None
        mock_link.idp_refresh_token_updated_at = None

        mock_idp = MagicMock()
        mock_idp.id = 1
        mock_idp.name = "TestIdP"
        mock_idp.slug = "test-idp"
        mock_idp.icon = "https://example.com/icon.svg"
        mock_idp.icon_uploaded = False
        mock_idp.provider_type = "oidc"

        with patch(
            "modules.auth.identity_providers.crud.get_identity_providers_by_ids",
            return_value=[mock_idp],
        ) as mock_get_idps:
            result = identity_links_utils.enrich_user_identity_providers([mock_link], 1, mock_db)

        assert len(result) == 1
        assert isinstance(result[0], IdentityProviderLinkRead)
        assert result[0].idp_name == "TestIdP"
        assert result[0].idp_slug == "test-idp"
        assert result[0].idp_icon == "https://example.com/icon.svg"
        assert result[0].idp_provider_type == "oidc"
        mock_get_idps.assert_called_once_with([1], mock_db)

    def test_skips_link_when_idp_not_found(self, mock_db):
        """
        Skips and logs warning when IdP missing from batch fetch.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - Returns empty list when IdP not in map.
        """
        now = datetime.now(UTC)

        mock_link = MagicMock()
        mock_link.id = 1
        mock_link.user_id = 1
        mock_link.idp_id = 99
        mock_link.idp_subject = "sub-xyz"
        mock_link.linked_at = now
        mock_link.last_login = None
        mock_link.idp_access_token_expires_at = None
        mock_link.idp_refresh_token_updated_at = None

        with patch(
            "modules.auth.identity_providers.crud.get_identity_providers_by_ids",
            return_value=[],
        ):
            result = identity_links_utils.enrich_user_identity_providers([mock_link], 1, mock_db)

        assert result == []

    def test_batch_fetches_all_idps_in_one_query(self, mock_db):
        """
        Uses a single batch query for all IdP IDs.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - get_identity_providers_by_ids called once with all IDs.
        """
        now = datetime.now(UTC)

        mock_links = []
        for i in range(1, 4):
            link = MagicMock()
            link.id = i
            link.user_id = 1
            link.idp_id = i
            link.idp_subject = f"sub-{i}"
            link.linked_at = now
            link.last_login = None
            link.idp_access_token_expires_at = None
            link.idp_refresh_token_updated_at = None
            mock_links.append(link)

        mock_idps = []
        for i in range(1, 4):
            idp = MagicMock()
            idp.id = i
            idp.name = f"IdP {i}"
            idp.slug = f"idp-{i}"
            idp.icon = None
            idp.icon_uploaded = False
            idp.provider_type = "oidc"
            mock_idps.append(idp)

        with patch(
            "modules.auth.identity_providers.crud.get_identity_providers_by_ids",
            return_value=mock_idps,
        ) as mock_get_idps:
            result = identity_links_utils.enrich_user_identity_providers(mock_links, 1, mock_db)

        assert len(result) == 3
        mock_get_idps.assert_called_once_with([1, 2, 3], mock_db)


class TestIdentityLinkServiceOperations:
    """Tests for Identity-link service operations.

    Note: link_external_identity and unlink_external_identity were removed from
    The identity-provider links module exposes its own integration behavior; operations are handled by
    auth.identity_link_service. This class is retained as a placeholder.
    """
