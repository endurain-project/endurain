"""
Tests for IdentityProviderService._find_or_create_user email-link gating.

Focuses on the account-takeover prevention introduced for email-based
linking: an external identity may only be auto-linked to an EXISTING local
account when the IdP asserts a verified email (OIDC ``email_verified``).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

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

    @pytest.mark.asyncio
    async def test_unverified_email_existing_account_is_rejected(self):
        """Linking to an existing account must fail when email unverified."""
        service = IdentityProviderService()
        idp = _make_idp()
        mock_db = MagicMock(spec=Session)
        password_hasher = MagicMock()
        existing_user = MagicMock()
        existing_user.username = "victim"

        userinfo = {"email": "victim@example.com"}  # no email_verified claim

        with (
            patch(
                "modules.auth.identity_providers.service.auth_identity_links_crud.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(
                "modules.auth.identity_providers.service.users_crud.get_user_by_email",
                return_value=existing_user,
            ),
            patch(
                "modules.auth.identity_providers.service.auth_identity_links_crud.create_user_identity_provider",
            ) as mock_link,
            pytest.raises(HTTPException) as exc_info,
        ):
            await service._find_or_create_user(idp, "subject-123", userinfo, password_hasher, mock_db)

        assert exc_info.value.status_code == 403
        # No link must be created for the unverified takeover attempt.
        mock_link.assert_not_called()

    @pytest.mark.asyncio
    async def test_verified_email_existing_account_is_linked(self):
        """Linking to an existing account succeeds when email is verified."""
        service = IdentityProviderService()
        idp = _make_idp()
        mock_db = MagicMock(spec=Session)
        password_hasher = MagicMock()
        existing_user = MagicMock()
        existing_user.id = 7
        existing_user.username = "legit"

        userinfo = {"email": "legit@example.com", "email_verified": True}

        with (
            patch(
                "modules.auth.identity_providers.service.auth_identity_links_crud.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(
                "modules.auth.identity_providers.service.users_crud.get_user_by_email",
                return_value=existing_user,
            ),
            patch(
                "modules.auth.identity_providers.service.auth_identity_links_crud.create_user_identity_provider",
            ) as mock_link,
        ):
            result = await service._find_or_create_user(idp, "subject-123", userinfo, password_hasher, mock_db)

        assert result is existing_user
        mock_link.assert_called_once_with(existing_user.id, idp.id, "subject-123", mock_db)

    @pytest.mark.asyncio
    async def test_unverified_email_no_existing_account_creates_user(self):
        """Unverified email with no existing account still auto-creates."""
        service = IdentityProviderService()
        idp = _make_idp()
        mock_db = MagicMock(spec=Session)
        password_hasher = MagicMock()
        created_user = MagicMock()

        userinfo = {"email": "fresh@example.com"}  # unverified, no match

        with (
            patch(
                "modules.auth.identity_providers.service.auth_identity_links_crud.get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch(
                "modules.auth.identity_providers.service.users_crud.get_user_by_email",
                return_value=None,
            ),
            patch.object(
                service,
                "_create_user_from_idp",
                new=AsyncMock(return_value=created_user),
            ) as mock_create,
        ):
            result = await service._find_or_create_user(idp, "subject-123", userinfo, password_hasher, mock_db)

        assert result is created_user
        mock_create.assert_called_once()
