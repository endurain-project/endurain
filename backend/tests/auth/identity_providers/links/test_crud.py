"""Tests for auth.identity_providers.links.crud module."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

import core.exceptions as core_exceptions
from modules.auth.identity_providers.links import crud as identity_links_crud
from modules.auth.identity_providers.links.models import IdentityLink


class TestCheckUserIdentityProvidersByIdpId:
    """Tests for check_user_identity_providers_by_idp_id."""

    def test_returns_true_when_link_exists(self, mock_db):
        """
        Returns True when at least one user is linked.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - Returns True when scalar returns truthy.
        """
        mock_db.execute.return_value.scalar.return_value = True

        result = identity_links_crud.check_user_identity_providers_by_idp_id(1, mock_db)

        assert result is True
        mock_db.execute.assert_called_once()

    def test_returns_false_when_no_links(self, mock_db):
        """
        Returns False when no users are linked to the IdP.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - Returns False when scalar returns None.
        """
        mock_db.execute.return_value.scalar.return_value = None

        result = identity_links_crud.check_user_identity_providers_by_idp_id(1, mock_db)

        assert result is False

    def test_raises_500_on_database_error(self, mock_db):
        """
        Raises HTTPException 500 on database error.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - HTTPException with status 500 raised.
        """
        mock_db.execute.side_effect = SQLAlchemyError("db error")

        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            identity_links_crud.check_user_identity_providers_by_idp_id(1, mock_db)

        assert exc_info.value.status_code == 500


class TestGetUserIdentityProvidersByUserId:
    """Tests for get_user_identity_providers_by_user_id."""

    def test_returns_list_of_links(self, mock_db):
        """
        Returns all identity provider links for a user.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - Returns list of IdentityLink objects.
        """
        mock_link1 = MagicMock(spec=IdentityLink)
        mock_link1.idp_id = 1
        mock_link2 = MagicMock(spec=IdentityLink)
        mock_link2.idp_id = 2
        mock_db.execute.return_value.scalars.return_value.all.return_value = [
            mock_link1,
            mock_link2,
        ]

        result = identity_links_crud.get_user_identity_providers_by_user_id(1, mock_db)

        assert len(result) == 2
        assert result[0].idp_id == 1
        mock_db.execute.assert_called_once()

    def test_returns_empty_list_when_no_links(self, mock_db):
        """
        Returns empty list when user has no IdP links.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - Returns empty list.
        """
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        result = identity_links_crud.get_user_identity_providers_by_user_id(1, mock_db)

        assert result == []

    def test_raises_500_on_database_error(self, mock_db):
        """
        Raises HTTPException 500 on database error.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - HTTPException with status 500 raised.
        """
        mock_db.execute.side_effect = SQLAlchemyError("db error")

        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            identity_links_crud.get_user_identity_providers_by_user_id(1, mock_db)

        assert exc_info.value.status_code == 500


class TestGetUserIdentityProviderByUserIdAndIdpId:
    """Tests for get_user_identity_provider_by_user_id_and_idp_id."""

    def test_returns_link_when_found(self, mock_db):
        """
        Returns the link when found for user + IdP.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - Returns IdentityLink object.
        """
        mock_link = MagicMock(spec=IdentityLink)
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_link

        result = identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id(1, 2, mock_db)

        assert result is mock_link

    def test_returns_none_when_not_found(self, mock_db):
        """
        Returns None when no link exists for user + IdP.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - Returns None.
        """
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        result = identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id(1, 2, mock_db)

        assert result is None

    def test_raises_500_on_database_error(self, mock_db):
        """
        Raises HTTPException 500 on database error.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - HTTPException with status 500 raised.
        """
        mock_db.execute.side_effect = SQLAlchemyError("db error")

        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id(1, 2, mock_db)

        assert exc_info.value.status_code == 500


class TestGetUserIdentityProviderBySubjectAndIdpId:
    """Tests for get_user_identity_provider_by_subject_and_idp_id."""

    def test_returns_link_when_found(self, mock_db):
        """
        Returns the link when found by provider + subject.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - Returns the matched IdentityLink.
        """
        mock_link = MagicMock(spec=IdentityLink)
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_link

        result = identity_links_crud.get_user_identity_provider_by_subject_and_idp_id(1, "user-sub-123", mock_db)

        assert result is mock_link

    def test_returns_none_when_not_found(self, mock_db):
        """
        Returns None when no link exists for provider + subject.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - Returns None.
        """
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        result = identity_links_crud.get_user_identity_provider_by_subject_and_idp_id(1, "unknown-sub", mock_db)

        assert result is None


class TestCreateUserIdentityProvider:
    """Tests for create_user_identity_provider."""

    def test_creates_and_returns_link(self, mock_db):
        """
        Creates and returns a new user-IdP link.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - db.add and db.commit called.
            - Returns the new IdentityLink.
        """
        mock_link = MagicMock(spec=IdentityLink)
        mock_db.refresh.side_effect = lambda obj: None

        with patch(
            "modules.auth.identity_providers.links.crud.auth_identity_links_models.IdentityLink",
            return_value=mock_link,
        ):
            result = identity_links_crud.create_user_identity_provider(
                user_id=1,
                idp_id=2,
                idp_subject="sub-abc",
                db=mock_db,
            )

        mock_db.add.assert_called_once_with(mock_link)
        mock_db.commit.assert_called()
        assert result is mock_link

    def test_raises_500_on_database_error(self, mock_db):
        """
        Raises HTTPException 500 on database error.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - HTTPException with status 500 raised.
        """
        mock_db.add.side_effect = SQLAlchemyError("db error")

        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            identity_links_crud.create_user_identity_provider(1, 2, "sub-abc", mock_db)

        assert exc_info.value.status_code == 500

    def test_raises_409_on_duplicate_link(self, mock_db):
        """
        Raises HTTPException 409 when the link already exists (IntegrityError).

        Args:
            mock_db: Mocked database session.

        Asserts:
            - HTTPException with status 409 raised.
            - db.rollback called.
        """
        mock_link = MagicMock(spec=IdentityLink)
        mock_db.commit.side_effect = IntegrityError("unique constraint", {}, None)

        with (
            patch(
                "modules.auth.identity_providers.links.crud.auth_identity_links_models.IdentityLink",
                return_value=mock_link,
            ),
            pytest.raises(HTTPException) as exc_info,
        ):
            identity_links_crud.create_user_identity_provider(1, 2, "sub-abc", mock_db)

        assert exc_info.value.status_code == 409
        assert "already linked" in exc_info.value.detail
        mock_db.rollback.assert_called_once()


class TestDeleteUserIdentityProvider:
    """Tests for delete_user_identity_provider."""

    def test_deletes_link_and_returns_true(self, mock_db):
        """
        Clears tokens, deletes link, returns True.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - Returns True on successful deletion.
            - db.delete and db.commit called.
        """
        mock_link = MagicMock(spec=IdentityLink)
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_link

        result = identity_links_crud.delete_user_identity_provider(1, 2, mock_db)

        assert result is True
        mock_db.delete.assert_called_once_with(mock_link)
        assert mock_db.commit.call_count >= 2

    def test_returns_false_when_link_not_found(self, mock_db):
        """
        Returns False when link does not exist.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - Returns False, no db.delete called.
        """
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        result = identity_links_crud.delete_user_identity_provider(1, 2, mock_db)

        assert result is False
        mock_db.delete.assert_not_called()

    def test_raises_500_on_database_error(self, mock_db):
        """
        Raises HTTPException 500 on database error.

        Args:
            mock_db: Mocked database session.

        Asserts:
            - HTTPException with status 500 raised.
        """
        mock_db.execute.side_effect = SQLAlchemyError("db error")

        with pytest.raises(core_exceptions.ProcessingError) as exc_info:
            identity_links_crud.delete_user_identity_provider(1, 2, mock_db)

        assert exc_info.value.status_code == 500
