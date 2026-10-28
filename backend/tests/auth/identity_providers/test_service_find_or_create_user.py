"""
Tests for IdentityProviderService._find_or_create_user email-link gating.

Focuses on the account-takeover prevention introduced for email-based
linking: an external identity may only be auto-linked to an EXISTING local
account when the IdP asserts a verified email (OIDC ``email_verified``).
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

import core.exceptions as core_exceptions
from modules.auth.identity_providers.service import IdentityProviderService


def _make_idp() -> MagicMock:
    """Build a minimal IdP mock that maps the standard email claim."""
    idp = MagicMock()
    idp.id = 1
    idp.name = "TestIdP"
    idp.user_mapping = None
    idp.sync_user_info = False
    idp.auto_create_users = True
    return idp


class TestIsEmailVerified:
    """Unit tests for the _is_email_verified claim parser."""

    @pytest.mark.parametrize(
        ("claims", "expected"),
        [
            ({"email_verified": True}, True),
            ({"email_verified": "true"}, True),
            ({"email_verified": "True"}, True),
            ({"email_verified": " TRUE "}, True),
            ({"email_verified": False}, False),
            ({"email_verified": "false"}, False),
            ({"email_verified": "1"}, False),
            ({"email_verified": 1}, False),
            ({"email_verified": None}, False),
            ({}, False),
        ],
    )
    def test_is_email_verified(self, claims, expected):
        """Only an explicit boolean/'true' assertion counts as verified."""
        assert IdentityProviderService._is_email_verified(claims) is expected


class TestFindOrCreateUserEmailLinking:
    """Test suite for email-based linking gate in _find_or_create_user."""

    def test_unverified_email_existing_account_is_rejected(self):
        """Linking to an existing account must fail when email unverified."""
        service = IdentityProviderService(MagicMock(), "https://app.example", "test")
        idp = _make_idp()
        mock_db = MagicMock(spec=Session)
        password_hasher = MagicMock()
        existing_user = MagicMock()
        existing_user.username = "victim"

        userinfo = {"email": "victim@example.com"}  # no email_verified claim

        with (
            patch(
                "modules.auth.identity_providers.service.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(
                "modules.auth.identity_providers.service.users_integration.get_user_by_email",
                return_value=existing_user,
            ),
            patch(
                "modules.auth.identity_providers.service.identity_provider_links_integration.create_user_identity_provider",
            ) as mock_link,
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service._find_or_create_user(idp, "subject-123", userinfo, password_hasher, mock_db)

        assert exc_info.value.status_code == 403
        # No link must be created for the unverified takeover attempt.
        mock_link.assert_not_called()

    def test_verified_email_existing_account_is_linked(self):
        """Linking to an existing account succeeds when email is verified."""
        service = IdentityProviderService(MagicMock(), "https://app.example", "test")
        idp = _make_idp()
        mock_db = MagicMock(spec=Session)
        password_hasher = MagicMock()
        existing_user = MagicMock()
        existing_user.id = 7
        existing_user.username = "legit"

        userinfo = {"email": "legit@example.com", "email_verified": True}

        with (
            patch(
                "modules.auth.identity_providers.service.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(
                "modules.auth.identity_providers.service.users_integration.get_user_by_email",
                return_value=existing_user,
            ),
            patch(
                "modules.auth.identity_providers.service.identity_provider_links_integration.create_user_identity_provider",
            ) as mock_link,
        ):
            result = service._find_or_create_user(idp, "subject-123", userinfo, password_hasher, mock_db)

        assert result is existing_user
        mock_link.assert_called_once_with(existing_user.id, idp.id, "subject-123", mock_db)

    def test_unverified_email_no_existing_account_creates_user(self):
        """Unverified email with no existing account still auto-creates."""
        service = IdentityProviderService(MagicMock(), "https://app.example", "test")
        idp = _make_idp()
        mock_db = MagicMock(spec=Session)
        password_hasher = MagicMock()
        created_user = MagicMock()

        userinfo = {"email": "fresh@example.com"}  # unverified, no match

        with (
            patch(
                "modules.auth.identity_providers.service.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(
                "modules.auth.identity_providers.service.users_integration.get_user_by_email",
                return_value=None,
            ),
            patch.object(
                service,
                "_create_user_from_idp",
                new=MagicMock(return_value=created_user),
            ) as mock_create,
        ):
            result = service._find_or_create_user(idp, "subject-123", userinfo, password_hasher, mock_db)

        assert result is created_user
        mock_create.assert_called_once()


class TestLocalEmailVerificationGate:
    """An email-based link also requires the local account's email to be verified."""

    def test_verified_idp_email_with_unverified_local_email_is_rejected(self):
        service = IdentityProviderService(MagicMock(), "https://app.example", "test")
        idp = _make_idp()
        mock_db = MagicMock(spec=Session)
        existing_user = MagicMock()
        existing_user.username = "victim"
        existing_user.email_verified = False

        userinfo = {"email": "victim@example.com", "email_verified": True}

        with (
            patch(
                "modules.auth.identity_providers.service.identity_provider_links_integration.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(
                "modules.auth.identity_providers.service.users_integration.get_user_by_email",
                return_value=existing_user,
            ),
            patch(
                "modules.auth.identity_providers.service.identity_provider_links_integration.create_user_identity_provider",
            ) as mock_link,
            pytest.raises(core_exceptions.DomainError) as exc_info,
        ):
            service._find_or_create_user(idp, "subject-123", userinfo, MagicMock(), mock_db)

        assert exc_info.value.status_code == 403
        mock_link.assert_not_called()


class TestUpdateUserFromIdpEmail:
    """The IdP email is synced onto a user only when the IdP asserts it is verified."""

    @staticmethod
    def _sync(userinfo):
        service = IdentityProviderService(MagicMock(), "https://app.example", "test")
        user = MagicMock()
        user.email = "old@example.com"
        user.name = "Same"
        idp = _make_idp()
        with (
            patch(
                "modules.auth.identity_providers.service.users_integration.get_user_by_email",
                return_value=None,
            ),
            patch("modules.auth.identity_providers.service.users_integration.edit_user") as mock_edit,
            patch("modules.auth.identity_providers.service.users_schema.UsersEdit.from_read"),
        ):
            service._update_user_from_idp(user, idp, userinfo, MagicMock(spec=Session))
        return user, mock_edit

    def test_unverified_idp_email_is_not_synced(self):
        user, mock_edit = self._sync({"email": "new@example.com", "name": "Same"})

        user.model_copy.assert_not_called()
        mock_edit.assert_not_called()

    def test_verified_idp_email_is_synced(self):
        user, mock_edit = self._sync({"email": "new@example.com", "name": "Same", "email_verified": True})

        user.model_copy.assert_called_once_with(update={"email": "new@example.com"})
        mock_edit.assert_called_once()
