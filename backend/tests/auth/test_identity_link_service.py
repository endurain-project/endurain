"""Service-level tests for auth.identity_link_service."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.account_security.identity_link_service as identity_link_service
import modules.auth.identity_provider_links.schema as auth_identity_links_schema
import modules.auth.identity_providers.constants as identity_providers_constants
import modules.users.users.schema as users_schema


class TestGetUserIdentityProviderLinks:
    """get_user_identity_provider_links: one page of a user's links, enriched with provider details."""

    def test_enriches_the_requested_window_and_counts_every_link(self, mock_db):
        link = MagicMock()
        enriched = auth_identity_links_schema.IdentityProviderLinkRead(
            id=1, user_id=1, idp_id=2, idp_subject="sub", linked_at=datetime(2026, 1, 1, tzinfo=UTC)
        )
        links = identity_link_service.identity_provider_links_integration

        with (
            patch.object(links, "get_identity_links_page", return_value=[link]) as get_page,
            patch.object(links, "count_identity_links", return_value=3),
            patch.object(
                identity_link_service.identity_providers_integration,
                "enrich_user_identity_providers",
                return_value=[enriched],
            ) as enrich,
        ):
            result = identity_link_service.get_user_identity_provider_links(
                1, core_pagination.PageParams(2, 1), mock_db
            )

        get_page.assert_called_once_with(1, mock_db, limit=1, offset=1)
        enrich.assert_called_once_with([link], 1, mock_db)
        assert result == auth_identity_links_schema.IdentityProviderLinkPage.build([enriched], 3, 2, 1)


class TestGetIdentityLinkCountsForUsers:
    """get_identity_link_counts_for_users: delegates to CRUD batch query."""

    def test_delegates_to_crud(self, mock_db):
        expected = {1: 2, 2: 1}
        with patch(
            "modules.auth.account_security.identity_link_service.identity_provider_links_integration.get_identity_link_counts_for_users",
            return_value=expected,
        ) as mock_crud:
            result = identity_link_service.get_identity_link_counts_for_users([1, 2], mock_db)

        assert result == expected
        mock_crud.assert_called_once_with([1, 2], mock_db)


class TestStartIdpLink:
    """start_idp_link: step-up verified before the browser link is staged."""

    _MODULE = "modules.auth.account_security.identity_link_service"

    def _make_idp(self, enabled=True, name="TestIDP"):
        idp = MagicMock()
        idp.enabled = enabled
        idp.name = name
        return idp

    def _link(self, redirect="/settings/security"):
        return users_schema.IdentityProviderLinkStart(current_password="pass", redirect=redirect)

    def test_commits_the_state_before_building_the_provider_url(self, mock_db):
        order = MagicMock()
        order.attach_mock(mock_db.commit, "commit")
        link = self._link()
        with (
            patch(f"{self._MODULE}.step_up_service.verify_step_up_credentials") as verify,
            patch(
                f"{self._MODULE}.identity_providers_integration.get_identity_provider", return_value=self._make_idp()
            ),
            patch(
                f"{self._MODULE}.identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=None,
            ),
            patch(
                f"{self._MODULE}.identity_providers_integration.stage_browser_link",
                return_value=MagicMock(browser_binding="binding"),
            ) as stage,
            patch(
                f"{self._MODULE}.identity_providers_integration.authorization_url",
                return_value="https://idp.example.com/auth",
            ) as build,
        ):
            order.attach_mock(build, "build_url")
            flow = identity_link_service.start_idp_link(1, link, "127.0.0.1", 10, "sid", MagicMock(), mock_db)

        verify.assert_called_once()
        assert verify.call_args.kwargs["action"] == identity_providers_constants.StepUpAction.IDP_LINK
        stage.assert_called_once_with(10, 1, "/settings/security", "127.0.0.1", mock_db)
        assert [call[0] for call in order.mock_calls] == ["commit", "build_url"]
        assert flow.authorization_url == "https://idp.example.com/auth"
        assert flow.browser_binding == "binding"

    def test_a_bad_redirect_is_refused_before_step_up_runs(self, mock_db):
        with (
            patch(f"{self._MODULE}.step_up_service.verify_step_up_credentials") as verify_step_up,
            patch(f"{self._MODULE}.identity_providers_integration.stage_browser_link") as stage,
            pytest.raises(core_exceptions.DomainError) as exc,
        ):
            identity_link_service.start_idp_link(
                1, self._link(redirect="https://evil.example.com"), "127.0.0.1", 10, "sid", MagicMock(), mock_db
            )

        assert exc.value.status_code == 400
        verify_step_up.assert_not_called()
        stage.assert_not_called()

    def test_raises_404_when_idp_not_found(self, mock_db):
        with (
            patch(f"{self._MODULE}.step_up_service.verify_step_up_credentials") as verify_step_up,
            patch(f"{self._MODULE}.identity_providers_integration.get_identity_provider", return_value=None),
            pytest.raises(core_exceptions.DomainError) as exc,
        ):
            identity_link_service.start_idp_link(1, self._link(), "127.0.0.1", 10, "sid", MagicMock(), mock_db)

        assert exc.value.status_code == 404
        verify_step_up.assert_not_called()

    def test_raises_404_when_idp_disabled(self, mock_db):
        with (
            patch(f"{self._MODULE}.step_up_service.verify_step_up_credentials") as verify_step_up,
            patch(
                f"{self._MODULE}.identity_providers_integration.get_identity_provider",
                return_value=self._make_idp(enabled=False),
            ),
            pytest.raises(core_exceptions.DomainError) as exc,
        ):
            identity_link_service.start_idp_link(1, self._link(), "127.0.0.1", 10, "sid", MagicMock(), mock_db)

        assert exc.value.status_code == 404
        verify_step_up.assert_not_called()

    def test_raises_409_when_already_linked(self, mock_db):
        with (
            patch(f"{self._MODULE}.step_up_service.verify_step_up_credentials") as verify_step_up,
            patch(
                f"{self._MODULE}.identity_providers_integration.get_identity_provider", return_value=self._make_idp()
            ),
            patch(
                f"{self._MODULE}.identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=MagicMock(),
            ),
            pytest.raises(core_exceptions.DomainError) as exc,
        ):
            identity_link_service.start_idp_link(1, self._link(), "127.0.0.1", 10, "sid", MagicMock(), mock_db)

        assert exc.value.status_code == 409
        verify_step_up.assert_not_called()

    def test_step_up_failure_stages_nothing(self, mock_db):
        with (
            patch(
                f"{self._MODULE}.identity_providers_integration.get_identity_provider", return_value=self._make_idp()
            ),
            patch(
                f"{self._MODULE}.identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=None,
            ),
            patch(
                f"{self._MODULE}.step_up_service.verify_step_up_credentials",
                side_effect=core_exceptions.UnauthenticatedError("Step-up verification failed"),
            ),
            patch(f"{self._MODULE}.identity_providers_integration.stage_browser_link") as stage,
            pytest.raises(core_exceptions.DomainError) as exc,
        ):
            identity_link_service.start_idp_link(1, self._link(), "127.0.0.1", 10, "sid", MagicMock(), mock_db)

        assert exc.value.status_code == 401
        stage.assert_not_called()
        mock_db.commit.assert_not_called()


class TestDeleteIdentityProviderLink:
    """delete_identity_provider_link: anti-lockout check before unlink."""

    def test_unlinks_successfully(self, mock_db):
        step_up = MagicMock()
        existing_links = [MagicMock(), MagicMock()]  # 2 links, so one can be removed

        with (
            patch("modules.auth.account_security.identity_link_service.step_up_service.verify_step_up_credentials"),
            patch(
                "modules.auth.account_security.identity_link_service.identity_providers_integration.get_identity_provider",
                return_value=MagicMock(name="TestIDP"),
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=MagicMock(),
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.get_user_identity_providers_by_user_id",
                return_value=existing_links,
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.delete_user_identity_provider",
                return_value=True,
            ),
            patch(
                "modules.auth.account_security.identity_link_service.credentials_integration.has_local_password",
                return_value=True,
            ),
        ):
            identity_link_service.delete_identity_provider_link(1, step_up, 10, "sid", MagicMock(), mock_db)

    def test_raises_404_when_idp_not_found(self, mock_db):
        with (
            patch(
                "modules.auth.account_security.identity_link_service.step_up_service.verify_step_up_credentials"
            ) as verify_step_up,
            patch(
                "modules.auth.account_security.identity_link_service.identity_providers_integration.get_identity_provider",
                return_value=None,
            ),
            pytest.raises(core_exceptions.DomainError) as exc,
        ):
            identity_link_service.delete_identity_provider_link(1, MagicMock(), 10, "sid", MagicMock(), mock_db)

        assert exc.value.status_code == 404
        verify_step_up.assert_not_called()

    def test_raises_404_when_link_not_found(self, mock_db):
        with (
            patch(
                "modules.auth.account_security.identity_link_service.step_up_service.verify_step_up_credentials"
            ) as verify_step_up,
            patch(
                "modules.auth.account_security.identity_link_service.identity_providers_integration.get_identity_provider",
                return_value=MagicMock(),
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=None,
            ),
            pytest.raises(core_exceptions.DomainError) as exc,
        ):
            identity_link_service.delete_identity_provider_link(1, MagicMock(), 10, "sid", MagicMock(), mock_db)

        assert exc.value.status_code == 404
        verify_step_up.assert_not_called()

    def test_raises_400_when_last_auth_method(self, mock_db):
        """Cannot unlink the last IdP when the user has no password."""

        with (
            patch(
                "modules.auth.account_security.identity_link_service.step_up_service.verify_step_up_credentials"
            ) as verify_step_up,
            patch(
                "modules.auth.account_security.identity_link_service.identity_providers_integration.get_identity_provider",
                return_value=MagicMock(),
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=MagicMock(),
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.get_user_identity_providers_by_user_id",
                return_value=[MagicMock()],  # exactly 1 link → remaining_idp_count == 0
            ),
            patch(
                "modules.auth.account_security.identity_link_service.credentials_integration.has_local_password",
                return_value=False,
            ),
            pytest.raises(core_exceptions.DomainError) as exc,
        ):
            identity_link_service.delete_identity_provider_link(1, MagicMock(), 10, "sid", MagicMock(), mock_db)

        assert exc.value.status_code == 400
        assert "Cannot unlink last authentication method" in exc.value.detail
        verify_step_up.assert_not_called()


class TestAdminDeleteIdentityProviderLink:
    """admin_delete_identity_provider_link: admin unlink with anti-lockout check."""

    def test_unlinks_successfully(self, mock_db):
        existing_links = [MagicMock(), MagicMock()]  # 2 links, so one can be removed

        with (
            patch(
                "modules.auth.account_security.identity_link_service.identity_providers_integration.get_identity_provider",
                return_value=MagicMock(name="TestIDP"),
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=MagicMock(),
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.get_user_identity_providers_by_user_id",
                return_value=existing_links,
            ),
            patch(
                "modules.auth.account_security.identity_link_service.credentials_integration.has_local_password",
                return_value=False,  # no password, but more than one link remains
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.delete_user_identity_provider",
                return_value=True,
            ) as mock_delete,
        ):
            identity_link_service.admin_delete_identity_provider_link(5, 1, mock_db)

        mock_delete.assert_called_once_with(5, 1, mock_db)

    def test_raises_404_when_idp_not_found(self, mock_db):
        with (
            patch(
                "modules.auth.account_security.identity_link_service.identity_providers_integration.get_identity_provider",
                return_value=None,
            ),
            pytest.raises(core_exceptions.DomainError) as exc,
        ):
            identity_link_service.admin_delete_identity_provider_link(5, 1, mock_db)

        assert exc.value.status_code == 404

    def test_raises_404_when_link_not_found(self, mock_db):
        with (
            patch(
                "modules.auth.account_security.identity_link_service.identity_providers_integration.get_identity_provider",
                return_value=MagicMock(),
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=None,
            ),
            pytest.raises(core_exceptions.DomainError) as exc,
        ):
            identity_link_service.admin_delete_identity_provider_link(5, 1, mock_db)

        assert exc.value.status_code == 404

    def test_raises_400_when_last_auth_method(self, mock_db):
        """Admin cannot unlink the last IdP when the user has no password."""
        with (
            patch(
                "modules.auth.account_security.identity_link_service.identity_providers_integration.get_identity_provider",
                return_value=MagicMock(),
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=MagicMock(),
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.get_user_identity_providers_by_user_id",
                return_value=[MagicMock()],  # exactly 1 link → remaining_idp_count == 0
            ),
            patch(
                "modules.auth.account_security.identity_link_service.credentials_integration.has_local_password",
                return_value=False,
            ),
            patch(
                "modules.auth.account_security.identity_link_service.credentials_integration.has_local_password",
                return_value=False,  # SSO-only, no local password
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.delete_user_identity_provider",
            ) as mock_delete,
            pytest.raises(core_exceptions.DomainError) as exc,
        ):
            identity_link_service.admin_delete_identity_provider_link(5, 1, mock_db)

        assert exc.value.status_code == 400
        assert "Cannot unlink last authentication method" in exc.value.detail
        mock_delete.assert_not_called()

    def test_unlinks_last_idp_when_user_has_password(self, mock_db):
        """Removing the last IdP is allowed when a local password exists."""
        with (
            patch(
                "modules.auth.account_security.identity_link_service.identity_providers_integration.get_identity_provider",
                return_value=MagicMock(),
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=MagicMock(),
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.get_user_identity_providers_by_user_id",
                return_value=[MagicMock()],  # only 1 link → remaining_idp_count == 0
            ),
            patch(
                "modules.auth.account_security.identity_link_service.credentials_integration.has_local_password",
                return_value=True,  # has local password
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.delete_user_identity_provider",
                return_value=True,
            ) as mock_delete,
        ):
            identity_link_service.admin_delete_identity_provider_link(5, 1, mock_db)

        mock_delete.assert_called_once_with(5, 1, mock_db)

    def test_raises_500_when_delete_fails(self, mock_db):
        with (
            patch(
                "modules.auth.account_security.identity_link_service.identity_providers_integration.get_identity_provider",
                return_value=MagicMock(),
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.get_user_identity_provider_by_user_id_and_idp_id",
                return_value=MagicMock(),
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.get_user_identity_providers_by_user_id",
                return_value=[MagicMock(), MagicMock()],
            ),
            patch(
                "modules.auth.account_security.identity_link_service.credentials_integration.has_local_password",
                return_value=True,
            ),
            patch(
                "modules.auth.account_security.identity_link_service.identity_provider_links_integration.delete_user_identity_provider",
                return_value=False,
            ),
            pytest.raises(core_exceptions.DomainError) as exc,
        ):
            identity_link_service.admin_delete_identity_provider_link(5, 1, mock_db)

        assert exc.value.status_code == 500
