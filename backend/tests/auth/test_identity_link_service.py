"""Service-level tests for auth.identity_link_service."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import auth._internal.services.identity_link_service as identity_link_service


class TestGetUserIdentityProviderLinks:
    """get_user_identity_provider_links: returns enriched links for a user."""

    def test_returns_enriched_links(self, mock_db):
        mock_link = MagicMock()
        enriched = [MagicMock()]

        with (
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_providers_by_user_id",
                return_value=[mock_link],
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_utils.enrich_user_identity_providers",
                return_value=enriched,
            ),
        ):
            result = identity_link_service.get_user_identity_provider_links(1, mock_db)

        assert result is enriched

    def test_returns_empty_list_when_no_links(self, mock_db):
        with (
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_providers_by_user_id",
                return_value=[],
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_utils.enrich_user_identity_providers",
                return_value=[],
            ),
        ):
            result = identity_link_service.get_user_identity_provider_links(1, mock_db)

        assert result == []


class TestGetIdentityLinkCountsForUsers:
    """get_identity_link_counts_for_users: delegates to CRUD batch query."""

    def test_delegates_to_crud(self, mock_db):
        expected = {1: 2, 2: 1}
        with patch(
            "auth._internal.services.identity_link_service.auth_identity_links_crud.get_identity_link_counts_for_users",
            return_value=expected,
        ) as mock_crud:
            result = identity_link_service.get_identity_link_counts_for_users([1, 2], mock_db)

        assert result == expected
        mock_crud.assert_called_once_with([1, 2], mock_db)


class TestGenerateLinkToken:
    """generate_link_token: step-up verified before issuing IdP link token."""

    def _make_idp(self, enabled=True, name="TestIDP"):
        idp = MagicMock()
        idp.enabled = enabled
        idp.name = name
        return idp

    def test_returns_token_on_success(self, mock_db):
        mock_token = MagicMock()
        identity_service = MagicMock()
        step_up_store = MagicMock()
        link_request = MagicMock()
        link_request.current_password = "pass"
        link_request.mfa_code = None
        request = MagicMock()
        request.client.host = "127.0.0.1"

        with (
            patch("auth._internal.services.identity_link_service.step_up_service.verify_step_up_credentials"),
            patch(
                "auth._internal.services.identity_link_service.idp_crud.get_identity_provider",
                return_value=self._make_idp(),
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=None,
            ),
            patch(
                "auth._internal.services.identity_link_service.idp_link_token_utils.generate_idp_link_token",
                return_value=mock_token,
            ),
        ):
            result = identity_link_service.generate_link_token(
                1, link_request, request, 10, identity_service, step_up_store, mock_db
            )

        assert result is mock_token

    def test_raises_404_when_idp_not_found(self, mock_db):
        with (
            patch("auth._internal.services.identity_link_service.step_up_service.verify_step_up_credentials"),
            patch("auth._internal.services.identity_link_service.idp_crud.get_identity_provider", return_value=None),
            pytest.raises(HTTPException) as exc,
        ):
            identity_link_service.generate_link_token(
                1, MagicMock(), MagicMock(), 10, MagicMock(), MagicMock(), mock_db
            )

        assert exc.value.status_code == 404

    def test_raises_404_when_idp_disabled(self, mock_db):
        with (
            patch("auth._internal.services.identity_link_service.step_up_service.verify_step_up_credentials"),
            patch(
                "auth._internal.services.identity_link_service.idp_crud.get_identity_provider",
                return_value=self._make_idp(enabled=False),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            identity_link_service.generate_link_token(
                1, MagicMock(), MagicMock(), 10, MagicMock(), MagicMock(), mock_db
            )

        assert exc.value.status_code == 404

    def test_raises_409_when_already_linked(self, mock_db):
        existing_link = MagicMock()
        with (
            patch("auth._internal.services.identity_link_service.step_up_service.verify_step_up_credentials"),
            patch(
                "auth._internal.services.identity_link_service.idp_crud.get_identity_provider",
                return_value=self._make_idp(),
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=existing_link,
            ),
            pytest.raises(HTTPException) as exc,
        ):
            identity_link_service.generate_link_token(
                1, MagicMock(), MagicMock(), 10, MagicMock(), MagicMock(), mock_db
            )

        assert exc.value.status_code == 409

    def test_step_up_failure_propagates(self, mock_db):
        """Step-up 401/429 from verify_step_up_credentials propagates to caller."""
        with (
            patch(
                "auth._internal.services.identity_link_service.step_up_service.verify_step_up_credentials",
                side_effect=HTTPException(status_code=401, detail="Step-up verification failed"),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            identity_link_service.generate_link_token(
                1, MagicMock(), MagicMock(), 10, MagicMock(), MagicMock(), mock_db
            )

        assert exc.value.status_code == 401


class TestDeleteIdentityProviderLink:
    """delete_identity_provider_link: anti-lockout check before unlink."""

    def test_unlinks_successfully(self, mock_db):
        step_up = MagicMock()
        existing_links = [MagicMock(), MagicMock()]  # 2 links, so one can be removed

        with (
            patch("auth._internal.services.identity_link_service.step_up_service.verify_step_up_credentials"),
            patch(
                "auth._internal.services.identity_link_service.idp_crud.get_identity_provider",
                return_value=MagicMock(name="TestIDP"),
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=MagicMock(),
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_providers_by_user_id",
                return_value=existing_links,
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.delete_user_identity_provider",
                return_value=True,
            ),
        ):
            identity_link_service.delete_identity_provider_link(1, step_up, 10, MagicMock(), MagicMock(), mock_db)

    def test_raises_404_when_idp_not_found(self, mock_db):
        with (
            patch("auth._internal.services.identity_link_service.step_up_service.verify_step_up_credentials"),
            patch("auth._internal.services.identity_link_service.idp_crud.get_identity_provider", return_value=None),
            pytest.raises(HTTPException) as exc,
        ):
            identity_link_service.delete_identity_provider_link(1, MagicMock(), 10, MagicMock(), MagicMock(), mock_db)

        assert exc.value.status_code == 404

    def test_raises_404_when_link_not_found(self, mock_db):
        with (
            patch("auth._internal.services.identity_link_service.step_up_service.verify_step_up_credentials"),
            patch(
                "auth._internal.services.identity_link_service.idp_crud.get_identity_provider",
                return_value=MagicMock(),
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=None,
            ),
            pytest.raises(HTTPException) as exc,
        ):
            identity_link_service.delete_identity_provider_link(1, MagicMock(), 10, MagicMock(), MagicMock(), mock_db)

        assert exc.value.status_code == 404

    def test_raises_400_when_last_auth_method(self, mock_db):
        """Cannot unlink the last IdP when the user has no password."""
        identity_service = MagicMock()
        identity_service.has_local_password.return_value = False  # SSO-only

        with (
            patch("auth._internal.services.identity_link_service.step_up_service.verify_step_up_credentials"),
            patch(
                "auth._internal.services.identity_link_service.idp_crud.get_identity_provider",
                return_value=MagicMock(),
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=MagicMock(),
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_providers_by_user_id",
                return_value=[MagicMock()],  # exactly 1 link → remaining_idp_count == 0
            ),
            pytest.raises(HTTPException) as exc,
        ):
            identity_link_service.delete_identity_provider_link(
                1, MagicMock(), 10, identity_service, MagicMock(), mock_db
            )

        assert exc.value.status_code == 400
        assert "Cannot unlink last authentication method" in exc.value.detail


class TestAdminDeleteIdentityProviderLink:
    """admin_delete_identity_provider_link: admin unlink with anti-lockout check."""

    def test_unlinks_successfully(self, mock_db):
        existing_links = [MagicMock(), MagicMock()]  # 2 links, so one can be removed

        with (
            patch(
                "auth._internal.services.identity_link_service.idp_crud.get_identity_provider",
                return_value=MagicMock(name="TestIDP"),
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=MagicMock(),
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_providers_by_user_id",
                return_value=existing_links,
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_credentials_crud.get_credential",
                return_value=None,  # no password, but more than one link remains
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.delete_user_identity_provider",
                return_value=True,
            ) as mock_delete,
        ):
            identity_link_service.admin_delete_identity_provider_link(5, 1, mock_db)

        mock_delete.assert_called_once_with(5, 1, mock_db)

    def test_raises_404_when_idp_not_found(self, mock_db):
        with (
            patch("auth._internal.services.identity_link_service.idp_crud.get_identity_provider", return_value=None),
            pytest.raises(HTTPException) as exc,
        ):
            identity_link_service.admin_delete_identity_provider_link(5, 1, mock_db)

        assert exc.value.status_code == 404

    def test_raises_404_when_link_not_found(self, mock_db):
        with (
            patch(
                "auth._internal.services.identity_link_service.idp_crud.get_identity_provider",
                return_value=MagicMock(),
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=None,
            ),
            pytest.raises(HTTPException) as exc,
        ):
            identity_link_service.admin_delete_identity_provider_link(5, 1, mock_db)

        assert exc.value.status_code == 404

    def test_raises_400_when_last_auth_method(self, mock_db):
        """Admin cannot unlink the last IdP when the user has no password."""
        with (
            patch(
                "auth._internal.services.identity_link_service.idp_crud.get_identity_provider",
                return_value=MagicMock(),
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=MagicMock(),
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_providers_by_user_id",
                return_value=[MagicMock()],  # exactly 1 link → remaining_idp_count == 0
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_credentials_crud.get_credential",
                return_value=None,  # SSO-only, no local password
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.delete_user_identity_provider",
            ) as mock_delete,
            pytest.raises(HTTPException) as exc,
        ):
            identity_link_service.admin_delete_identity_provider_link(5, 1, mock_db)

        assert exc.value.status_code == 400
        assert "Cannot unlink last authentication method" in exc.value.detail
        mock_delete.assert_not_called()

    def test_unlinks_last_idp_when_user_has_password(self, mock_db):
        """Removing the last IdP is allowed when a local password exists."""
        with (
            patch(
                "auth._internal.services.identity_link_service.idp_crud.get_identity_provider",
                return_value=MagicMock(),
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=MagicMock(),
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_providers_by_user_id",
                return_value=[MagicMock()],  # only 1 link → remaining_idp_count == 0
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_credentials_crud.get_credential",
                return_value=MagicMock(),  # has local password
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.delete_user_identity_provider",
                return_value=True,
            ) as mock_delete,
        ):
            identity_link_service.admin_delete_identity_provider_link(5, 1, mock_db)

        mock_delete.assert_called_once_with(5, 1, mock_db)

    def test_raises_500_when_delete_fails(self, mock_db):
        with (
            patch(
                "auth._internal.services.identity_link_service.idp_crud.get_identity_provider",
                return_value=MagicMock(),
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=MagicMock(),
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_providers_by_user_id",
                return_value=[MagicMock(), MagicMock()],
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_credentials_crud.get_credential",
                return_value=MagicMock(),
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.delete_user_identity_provider",
                return_value=False,
            ),
            pytest.raises(HTTPException) as exc,
        ):
            identity_link_service.admin_delete_identity_provider_link(5, 1, mock_db)

        assert exc.value.status_code == 500


class TestValidateAndClaimBrowserLinkToken:
    """validate_and_claim_browser_link_token: token validation and atomic claim."""

    def test_returns_user_id_on_success(self, mock_db):
        db_token = MagicMock()
        db_token.idp_id = 1
        db_token.ip_address = "127.0.0.1"
        db_token.user_id = 42

        with (
            patch(
                "auth._internal.services.identity_link_service.idp_link_token_utils.hash_idp_link_token",
                return_value="hash",
            ),
            patch(
                "auth._internal.services.identity_link_service.idp_link_token_crud.get_idp_link_token_by_hash",
                return_value=db_token,
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=None,
            ),
            patch(
                "auth._internal.services.identity_link_service.idp_link_token_crud.mark_token_as_used",
                return_value=True,
            ),
        ):
            result = identity_link_service.validate_and_claim_browser_link_token("tok", 1, "127.0.0.1", mock_db)

        assert result == 42

    def test_raises_401_when_token_not_found(self, mock_db):
        with (
            patch(
                "auth._internal.services.identity_link_service.idp_link_token_utils.hash_idp_link_token",
                return_value="hash",
            ),
            patch(
                "auth._internal.services.identity_link_service.idp_link_token_crud.get_idp_link_token_by_hash",
                return_value=None,
            ),
            pytest.raises(HTTPException) as exc,
        ):
            identity_link_service.validate_and_claim_browser_link_token("bad-token", 1, None, mock_db)

        assert exc.value.status_code == 401

    def test_raises_401_when_idp_mismatch(self, mock_db):
        db_token = MagicMock()
        db_token.idp_id = 2  # different from requested idp_id=1
        db_token.ip_address = None

        with (
            patch(
                "auth._internal.services.identity_link_service.idp_link_token_utils.hash_idp_link_token",
                return_value="hash",
            ),
            patch(
                "auth._internal.services.identity_link_service.idp_link_token_crud.get_idp_link_token_by_hash",
                return_value=db_token,
            ),
            pytest.raises(HTTPException) as exc,
        ):
            identity_link_service.validate_and_claim_browser_link_token("tok", 1, None, mock_db)

        assert exc.value.status_code == 401

    def test_raises_409_when_already_linked(self, mock_db):
        db_token = MagicMock()
        db_token.idp_id = 1
        db_token.ip_address = None
        db_token.user_id = 42

        with (
            patch(
                "auth._internal.services.identity_link_service.idp_link_token_utils.hash_idp_link_token",
                return_value="hash",
            ),
            patch(
                "auth._internal.services.identity_link_service.idp_link_token_crud.get_idp_link_token_by_hash",
                return_value=db_token,
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=MagicMock(),  # already exists
            ),
            pytest.raises(HTTPException) as exc,
        ):
            identity_link_service.validate_and_claim_browser_link_token("tok", 1, None, mock_db)

        assert exc.value.status_code == 409

    def test_raises_400_on_replay(self, mock_db):
        """Token that has already been used (mark_token_as_used returns False) raises 400."""
        db_token = MagicMock()
        db_token.idp_id = 1
        db_token.ip_address = None
        db_token.user_id = 42
        db_token.id = 7

        with (
            patch(
                "auth._internal.services.identity_link_service.idp_link_token_utils.hash_idp_link_token",
                return_value="hash",
            ),
            patch(
                "auth._internal.services.identity_link_service.idp_link_token_crud.get_idp_link_token_by_hash",
                return_value=db_token,
            ),
            patch(
                "auth._internal.services.identity_link_service.auth_identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=None,
            ),
            patch(
                "auth._internal.services.identity_link_service.idp_link_token_crud.mark_token_as_used",
                return_value=False,  # already used (race/replay)
            ),
            pytest.raises(HTTPException) as exc,
        ):
            identity_link_service.validate_and_claim_browser_link_token("tok", 1, None, mock_db)

        assert exc.value.status_code == 400
