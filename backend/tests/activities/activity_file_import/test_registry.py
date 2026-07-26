"""Tests for the activity file-parser registry."""

from unittest.mock import patch

import modules.activities.activity_file_import.registry as registry


class TestGetParser:
    def test_returns_parser_for_supported_extensions(self):
        assert registry.get_parser(".gpx") is not None
        assert registry.get_parser(".tcx") is not None
        assert registry.get_parser(".fit") is not None

    def test_is_case_insensitive(self):
        assert registry.get_parser(".GPX") is registry.get_parser(".gpx")

    def test_returns_none_for_unsupported_extension(self):
        assert registry.get_parser(".xyz") is None


class TestSupportedExtensions:
    def test_lists_registered_extensions(self):
        assert set(registry.supported_extensions()) == {".gpx", ".tcx", ".fit"}


class TestAdapters:
    @patch("modules.activities.activity_file_import.registry.gpx_utils")
    def test_gpx_adapter_normalizes_to_dict(self, mock_gpx):
        mock_gpx.parse_gpx_file.return_value = {"activity": "gpx"}
        parser = registry.get_parser(".gpx")
        assert parser("/f.gpx", 7, "Name", "Asia/Tokyo") == {"activity": "gpx"}
        mock_gpx.parse_gpx_file.assert_called_once_with("/f.gpx", 7, "Name", "Asia/Tokyo")

    @patch("modules.activities.activity_file_import.registry.tcx_utils")
    def test_tcx_adapter_forwards_the_fallback_timezone(self, mock_tcx):
        mock_tcx.parse_tcx_file.return_value = {"activity": "tcx"}
        parser = registry.get_parser(".tcx")
        assert parser("/f.tcx", 7, "Name", "Asia/Tokyo") == {"activity": "tcx"}
        mock_tcx.parse_tcx_file.assert_called_once_with("/f.tcx", 7, "Name", "Asia/Tokyo")

    @patch("modules.activities.activity_file_import.registry.gpx_utils")
    def test_fallback_timezone_is_optional(self, mock_gpx):
        mock_gpx.parse_gpx_file.return_value = {"activity": "gpx"}
        parser = registry.get_parser(".gpx")
        parser("/f.gpx", 7)
        mock_gpx.parse_gpx_file.assert_called_once_with("/f.gpx", 7, None, None)

    @patch("modules.activities.activity_file_import.registry.fit_utils")
    def test_fit_adapter_ignores_user_id_and_timezone(self, mock_fit):
        # FIT's parse stage is owner- and timezone-agnostic; both are applied
        # later, when create_activity_objects builds the ActivityCore.
        mock_fit.parse_fit_file.return_value = {"activity": "fit"}
        parser = registry.get_parser(".fit")
        assert parser("/f.fit", 7, "Name", "Asia/Tokyo") == {"activity": "fit"}
        mock_fit.parse_fit_file.assert_called_once_with("/f.fit", "Name")
