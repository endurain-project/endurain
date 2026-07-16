"""Tests for users.users.utils module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session


class TestGetUserByIdOr404:
    """get_user_by_id_or_404: retrieve user or raise 404."""

    def test_returns_user_when_found(self):
        from modules.users.users.utils import get_user_by_id_or_404

        mock_db = MagicMock(spec=Session)
        mock_user = MagicMock()

        with patch("modules.users.users.crud.get_user_by_id", return_value=mock_user):
            result = get_user_by_id_or_404(1, mock_db)

        assert result == mock_user

    def test_raises_404_when_user_is_none(self):
        from modules.users.users.utils import get_user_by_id_or_404

        mock_db = MagicMock(spec=Session)

        with patch("modules.users.users.crud.get_user_by_id", return_value=None), pytest.raises(HTTPException) as exc:
            get_user_by_id_or_404(1, mock_db)

        assert exc.value.status_code == 404


class TestGetAdminUsersOr404:
    """get_admin_users_or_404: retrieve admin users or raise 404."""

    def test_returns_admins_when_found(self):
        from modules.users.users.utils import get_admin_users_or_404

        mock_db = MagicMock(spec=Session)
        mock_admin = MagicMock()

        with patch("modules.users.users.crud.get_users_admin", return_value=[mock_admin]):
            result = get_admin_users_or_404(mock_db)

        assert result == [mock_admin]

    def test_raises_404_when_empty(self):
        from modules.users.users.utils import get_admin_users_or_404

        mock_db = MagicMock(spec=Session)

        with patch("modules.users.users.crud.get_users_admin", return_value=[]), pytest.raises(HTTPException) as exc:
            get_admin_users_or_404(mock_db)

        assert exc.value.status_code == 404


class TestCheckUserIsActive:
    """check_user_is_active: verify user is active."""

    def test_active_user_passes(self):
        from modules.users.users.utils import check_user_is_active

        mock_user = MagicMock()
        mock_user.active = True

        check_user_is_active(mock_user)

    def test_inactive_user_raises_403(self):
        from modules.users.users.utils import check_user_is_active

        mock_user = MagicMock()
        mock_user.active = False

        with pytest.raises(HTTPException) as exc:
            check_user_is_active(mock_user)

        assert exc.value.status_code == 403


class TestCreateUserDefaultData:
    """create_user_default_data: create default data for new user."""

    def test_calls_all_five_crud_functions(self):
        from modules.users.users.utils import create_user_default_data

        mock_db = MagicMock(spec=Session)
        mock_identity = MagicMock()

        with (
            patch("modules.users.users_integrations.crud.create_user_integrations") as mock_integrations,
            patch("modules.users.users_privacy_settings.crud.create_user_privacy_settings") as mock_privacy,
            patch("modules.health.health_targets.crud.create_health_targets") as mock_targets,
            patch("modules.users.users_default_gear.crud.create_user_default_gear") as mock_gear,
        ):
            create_user_default_data(1, mock_identity, mock_db)

        mock_integrations.assert_called_once_with(1, mock_db)
        mock_privacy.assert_called_once_with(1, mock_db)
        mock_targets.assert_called_once_with(1, mock_db)
        mock_gear.assert_called_once_with(1, mock_db)
        # MFA row is created through the auth boundary.
        mock_identity.initialize_user_mfa.assert_called_once_with(1)


class TestSaveUserImageFile:
    """save_user_image_file: validate and save user image."""

    @pytest.mark.asyncio
    async def test_raises_400_when_filename_is_none(self):
        from modules.users.users.utils import save_user_image_file

        mock_file = MagicMock()
        mock_file.filename = None
        mock_db = MagicMock(spec=Session)

        with (
            patch("modules.users.users.utils.get_user_by_id_or_404", return_value=MagicMock()),
            pytest.raises(HTTPException) as exc,
        ):
            await save_user_image_file(1, mock_file, mock_db)

        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_raises_400_when_filename_empty(self):
        from modules.users.users.utils import save_user_image_file

        mock_file = MagicMock()
        mock_file.filename = ""
        mock_db = MagicMock(spec=Session)

        with (
            patch("modules.users.users.utils.get_user_by_id_or_404", return_value=MagicMock()),
            pytest.raises(HTTPException) as exc,
        ):
            await save_user_image_file(1, mock_file, mock_db)

        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_raises_415_for_unsupported_extension(self):
        from modules.users.users.utils import save_user_image_file

        mock_file = MagicMock()
        mock_file.filename = "avatar.txt"
        mock_db = MagicMock(spec=Session)

        with (
            patch("modules.users.users.utils.get_user_by_id_or_404", return_value=MagicMock()),
            pytest.raises(HTTPException) as exc,
        ):
            await save_user_image_file(1, mock_file, mock_db)

        assert exc.value.status_code == 415

    @pytest.mark.asyncio
    async def test_success_saves_file_and_updates_db(self):
        from modules.users.users.utils import save_user_image_file

        mock_file = MagicMock()
        mock_file.filename = "avatar.png"
        mock_db = MagicMock(spec=Session)

        with (
            patch("modules.users.users.utils.get_user_by_id_or_404", return_value=MagicMock()),
            patch("core.file_uploads.save_validated_upload", new_callable=AsyncMock),
            patch(
                "modules.users.users.crud.update_user_photo",
                new_callable=AsyncMock,
                return_value="/path/to/user_images/1.png",
            ),
        ):
            result = await save_user_image_file(1, mock_file, mock_db)

        assert result == "/path/to/user_images/1.png"


class TestDeleteUserPhotoFilesystem:
    """delete_user_photo_filesystem: delete user photo files."""

    @pytest.mark.asyncio
    async def test_calls_delete_files_by_pattern(self):
        from modules.users.users.utils import delete_user_photo_filesystem

        with patch(
            "core.file_uploads.delete_files_by_pattern",
            new_callable=AsyncMock,
        ) as mock_delete:
            await delete_user_photo_filesystem(42)

        mock_delete.assert_called_once()
        args, _ = mock_delete.call_args
        assert args[1] == "42.*"
