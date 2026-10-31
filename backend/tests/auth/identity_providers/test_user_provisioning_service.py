"""
Tests for user_provisioning_service.find_or_create_user email-link gating.

Focuses on the account-takeover prevention introduced for email-based
linking: an external identity may only be auto-linked to an EXISTING local
account when the IdP asserts a verified email (OIDC ``email_verified``).
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
import modules.auth.identity_providers.user_provisioning_service as user_provisioning_service


def _make_idp() -> MagicMock:
    """Build a minimal IdP mock that maps the standard email claim."""
    idp = MagicMock()
    idp.id = 1
    idp.name = "TestIdP"
    idp.user_mapping = None
    idp.sync_user_info = False
    idp.auto_create_users = True
    return idp


class TestFindOrCreateUserEmailLinking:
    """Test suite for email-based linking gate in find_or_create_user."""

    def test_unverified_email_existing_account_is_rejected(self):
        """Linking to an existing account must fail when email unverified."""
        idp = _make_idp()
        mock_db = MagicMock(spec=Session)
        existing_user = MagicMock()
        existing_user.username = "victim"

        userinfo = {"email": "victim@example.com"}  # no email_verified claim

        with (
            patch(
                "modules.auth.identity_providers.user_provisioning_service.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(
                "modules.auth.identity_providers.user_provisioning_service.users_integration.get_user_by_email",
                return_value=existing_user,
            ),
            patch(
                "modules.auth.identity_providers.user_provisioning_service.identity_provider_links_integration.create_user_identity_provider",
            ) as mock_link,
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            user_provisioning_service.find_or_create_user(idp, "subject-123", userinfo, mock_db)

        assert exc_info.value.status_code == 403
        # No link must be created for the unverified takeover attempt.
        mock_link.assert_not_called()

    def test_verified_email_existing_account_is_linked(self):
        """Linking to an existing account succeeds when email is verified."""
        idp = _make_idp()
        mock_db = MagicMock(spec=Session)
        existing_user = MagicMock()
        existing_user.id = 7
        existing_user.username = "legit"

        userinfo = {"email": "legit@example.com", "email_verified": True}

        with (
            patch(
                "modules.auth.identity_providers.user_provisioning_service.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(
                "modules.auth.identity_providers.user_provisioning_service.users_integration.get_user_by_email",
                return_value=existing_user,
            ),
            patch(
                "modules.auth.identity_providers.user_provisioning_service.identity_provider_links_integration.create_user_identity_provider",
            ) as mock_link,
        ):
            result = user_provisioning_service.find_or_create_user(idp, "subject-123", userinfo, mock_db)

        assert result is existing_user
        mock_link.assert_called_once_with(existing_user.id, idp.id, "subject-123", mock_db)

    def test_unverified_email_no_existing_account_creates_user(self):
        """Unverified email with no existing account still auto-creates."""
        idp = _make_idp()
        mock_db = MagicMock(spec=Session)
        created_user = MagicMock()

        userinfo = {"email": "fresh@example.com"}  # unverified, no match

        with (
            patch(
                "modules.auth.identity_providers.user_provisioning_service.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(
                "modules.auth.identity_providers.user_provisioning_service.users_integration.get_user_by_email",
                return_value=None,
            ),
            patch.object(
                user_provisioning_service,
                "create_user_from_idp",
                new=MagicMock(return_value=created_user),
            ) as mock_create,
        ):
            result = user_provisioning_service.find_or_create_user(idp, "subject-123", userinfo, mock_db)

        assert result is created_user
        mock_create.assert_called_once()
        assert mock_create.call_args.kwargs["email_verified"] is False


class TestCreatedAccountEmailVerification:
    """A new SSO account's email is verified only when the provider asserted it as verified."""

    @pytest.mark.parametrize("asserted", [True, False])
    def test_the_flag_follows_the_provider(self, asserted):
        with (
            patch.object(user_provisioning_service.users_integration, "get_user_by_username", return_value=None),
            patch.object(user_provisioning_service.server_settings_integration, "get_server_settings"),
            patch.object(user_provisioning_service.users_integration, "create_sso_user") as create_sso_user,
            patch.object(
                user_provisioning_service.identity_provider_links_integration, "create_user_identity_provider"
            ),
        ):
            create_sso_user.return_value = MagicMock(id=3, username="new")
            user_provisioning_service.create_user_from_idp(
                _make_idp(),
                "subject-123",
                {"username": "new", "email": "new@example.com"},
                MagicMock(),
                email_verified=asserted,
            )

        assert create_sso_user.call_args.kwargs["email_verified"] is asserted

    def test_the_account_carries_the_mapped_profile(self):
        with (
            patch.object(user_provisioning_service.users_integration, "get_user_by_username", return_value=None),
            patch.object(user_provisioning_service.server_settings_integration, "get_server_settings"),
            patch.object(user_provisioning_service.users_integration, "create_sso_user") as create_sso_user,
            patch.object(
                user_provisioning_service.identity_provider_links_integration, "create_user_identity_provider"
            ),
        ):
            create_sso_user.return_value = MagicMock(id=3, username="new")
            user_provisioning_service.create_user_from_idp(
                _make_idp(),
                "subject-123",
                {"username": "new", "email": "new@example.com", "city": "Lisbon", "height": 180},
                MagicMock(),
                email_verified=True,
            )

        profile = create_sso_user.call_args.args[0]
        assert (profile.username, profile.city, profile.height) == ("new", "Lisbon", 180)

    @pytest.mark.parametrize("mapped", [{}, {"email": ""}, {"email": None}])
    def test_an_account_without_an_email_is_refused_with_its_own_reason(self, mapped):
        """Every account needs a real address for reset and notices, so none is invented for it."""
        with (
            patch.object(user_provisioning_service.users_integration, "create_sso_user") as create_sso_user,
            pytest.raises(user_provisioning_service.SsoSignInRefusedError) as exc_info,
        ):
            user_provisioning_service.create_user_from_idp(
                _make_idp(), "subject-123", {"username": "new", **mapped}, MagicMock(), email_verified=True
            )

        assert exc_info.value.login_error == "sso_email_missing"
        create_sso_user.assert_not_called()


class TestLocalEmailVerificationGate:
    """An email-based link also requires the local account's email to be verified."""

    def test_verified_idp_email_with_unverified_local_email_is_rejected(self):
        idp = _make_idp()
        mock_db = MagicMock(spec=Session)
        existing_user = MagicMock()
        existing_user.username = "victim"
        existing_user.email_verified = False

        userinfo = {"email": "victim@example.com", "email_verified": True}

        with (
            patch(
                "modules.auth.identity_providers.user_provisioning_service.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(
                "modules.auth.identity_providers.user_provisioning_service.users_integration.get_user_by_email",
                return_value=existing_user,
            ),
            patch(
                "modules.auth.identity_providers.user_provisioning_service.identity_provider_links_integration.create_user_identity_provider",
            ) as mock_link,
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            user_provisioning_service.find_or_create_user(idp, "subject-123", userinfo, mock_db)

        assert exc_info.value.status_code == 403
        mock_link.assert_not_called()


class TestUpdateUserFromIdpEmail:
    """The IdP email is synced onto a user only when the IdP asserts it is verified."""

    @staticmethod
    def _sync(userinfo):
        user = MagicMock()
        user.username = "alice"
        user.email = "old@example.com"
        user.name = "Same"
        idp = _make_idp()
        with (
            patch(
                "modules.auth.identity_providers.user_provisioning_service.users_integration.get_user_by_email",
                return_value=None,
            ),
            patch("modules.auth.identity_providers.user_provisioning_service.users_integration.edit_user") as mock_edit,
            patch("modules.auth.identity_providers.user_provisioning_service.users_schema.UsersEdit.from_read"),
        ):
            user_provisioning_service.update_user_from_idp(user, idp, userinfo, MagicMock(spec=Session))
        return user, mock_edit

    def test_unverified_idp_email_is_not_synced(self):
        user, mock_edit = self._sync({"email": "new@example.com", "name": "Same"})

        user.model_copy.assert_not_called()
        mock_edit.assert_not_called()

    def test_verified_idp_email_is_synced(self):
        user, mock_edit = self._sync({"email": "new@example.com", "name": "Same", "email_verified": True})

        user.model_copy.assert_called_once_with(update={"email": "new@example.com"})
        mock_edit.assert_called_once()


class TestUpdateUserFromIdpLogging:
    """Sync logging names the changed fields and a username fingerprint, never the values."""

    def test_applied_updates_log_field_names_and_hashed_username(self):
        user = MagicMock()
        user.username = "alice"
        user.email = "old@example.com"
        user.name = "Same"
        with (
            patch(
                "modules.auth.identity_providers.user_provisioning_service.users_integration.get_user_by_email",
                return_value=None,
            ),
            patch("modules.auth.identity_providers.user_provisioning_service.users_integration.edit_user"),
            patch("modules.auth.identity_providers.user_provisioning_service.users_schema.UsersEdit.from_read"),
            patch("modules.auth.identity_providers.user_provisioning_service.logger") as mock_logger,
        ):
            user_provisioning_service.update_user_from_idp(
                user,
                _make_idp(),
                {"email": "new@example.com", "name": "Same", "email_verified": True},
                MagicMock(spec=Session),
            )

        extra = mock_logger.info.call_args.kwargs["extra"]
        assert extra["updated_fields"] == ["email"]
        assert "updates" not in extra
        assert "alice" not in str(extra)
        assert "new@example.com" not in str(extra)
