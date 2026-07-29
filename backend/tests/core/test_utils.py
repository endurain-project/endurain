"""Tests for core.utils — path-safety and static-file serving."""

import os
from unittest.mock import MagicMock, patch


class TestSafeResolve:
    """Tests for _safe_resolve path-safety guard."""

    def test_empty_path_returns_none(self, tmp_path):
        from core.utils import _safe_resolve

        result = _safe_resolve(str(tmp_path), "")
        assert result is None

    def test_absolute_path_returns_none(self, tmp_path):
        from core.utils import _safe_resolve

        result = _safe_resolve(str(tmp_path), "/etc/passwd")
        assert result is None

    def test_valid_relative_path_resolves(self, tmp_path):
        from core.utils import _safe_resolve

        nested = tmp_path / "sub" / "file.txt"
        nested.parent.mkdir(parents=True)
        nested.write_text("content")

        result = _safe_resolve(str(tmp_path), "sub/file.txt")
        assert result == os.path.realpath(str(nested))

    def test_path_traversal_returns_none(self, tmp_path):
        from core.utils import _safe_resolve

        result = _safe_resolve(str(tmp_path), "../etc/passwd")
        assert result is None

    def test_nonexistent_file_returns_none(self, tmp_path):
        from core.utils import _safe_resolve

        result = _safe_resolve(str(tmp_path), "nonexistent.txt")
        assert result is None

    def test_symlink_inside_base_resolves(self, tmp_path):
        from core.utils import _safe_resolve

        target = tmp_path / "target.txt"
        target.write_text("content")
        link = tmp_path / "link.txt"
        link.symlink_to("target.txt")

        result = _safe_resolve(str(tmp_path), "link.txt")
        assert result == os.path.realpath(str(target))


class TestServeFrom:
    """Tests for _serve_from helper."""

    def test_returns_none_when_safe_resolve_fails(self, tmp_path):
        from core.utils import _serve_from

        result = _serve_from(str(tmp_path), "../etc/passwd")
        assert result is None

    def test_returns_file_response_for_valid_path(self, tmp_path):
        from fastapi.responses import FileResponse

        from core.utils import _serve_from

        child = tmp_path / "valid.txt"
        child.write_text("hello")

        result = _serve_from(str(tmp_path), "valid.txt")
        assert isinstance(result, FileResponse)


class TestReturnFrontendIndex:
    """Tests for return_frontend_index."""

    def test_calls_serve_from_with_frontend_dir(self):
        from core.utils import return_frontend_index

        mock_core_config = MagicMock()
        mock_core_config.settings.FRONTEND_DIR = "/mock/frontend"
        mock_serve_from = MagicMock(return_value="response")

        with patch.multiple(
            "core.utils",
            core_config=mock_core_config,
            _serve_from=mock_serve_from,
        ):
            result = return_frontend_index("index.html")

        mock_serve_from.assert_called_once_with("/mock/frontend", "index.html")
        assert result == "response"


class TestReturnUserImgPath:
    """Tests for return_user_img_path."""

    def test_calls_serve_from_with_user_images_dir(self):
        from core.utils import return_user_img_path

        mock_core_config = MagicMock()
        mock_core_config.USER_IMAGES_DIR = "/mock/user_images"
        mock_serve_from = MagicMock(return_value="response")

        with patch.multiple(
            "core.utils",
            core_config=mock_core_config,
            _serve_from=mock_serve_from,
        ):
            result = return_user_img_path("avatar.png")

        mock_serve_from.assert_called_once_with("/mock/user_images", "avatar.png")
        assert result == "response"


class TestReturnServerImgPath:
    """Tests for return_server_img_path."""

    def test_calls_serve_from_with_server_images_dir(self):
        from core.utils import return_server_img_path

        mock_core_config = MagicMock()
        mock_core_config.SERVER_IMAGES_DIR = "/mock/server_images"
        mock_serve_from = MagicMock(return_value="response")

        with patch.multiple(
            "core.utils",
            core_config=mock_core_config,
            _serve_from=mock_serve_from,
        ):
            result = return_server_img_path("banner.jpg")

        mock_serve_from.assert_called_once_with("/mock/server_images", "banner.jpg")
        assert result == "response"


class TestNoBlobPathHelpers:
    """Activity media and thumbnails must have no filename-addressed serve helper.

    Both are private user data served only through their token-gated routes. A
    ``return_*_path`` helper here is what the removed public routes were built
    on, so its absence is the regression guard.
    """

    def test_no_activity_media_path_helper(self):
        import core.utils

        assert not hasattr(core.utils, "return_activity_media_path")

    def test_no_activity_thumbnail_path_helper(self):
        import core.utils

        assert not hasattr(core.utils, "return_activity_thumbnail_path")
