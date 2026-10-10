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
    @patch("modules.activities.activity_file_import.registry.adapter")
    @patch("modules.activities.activity_file_import.registry.gpx_utils")
    def test_gpx_adapter_returns_a_single_activity_parsed_file(self, mock_gpx, mock_adapter):
        mock_gpx.parse_gpx_file.return_value = {"activity": "gpx"}
        mock_adapter.parsed_info_to_parsed_activity.return_value = "parsed-gpx"
        parser = registry.get_parser(".gpx")

        result = parser("/f.gpx", 7, "Name", "Asia/Tokyo")

        assert result.activities == ["parsed-gpx"]
        assert result.components == {}
        mock_gpx.parse_gpx_file.assert_called_once_with("/f.gpx", 7, "Name", "Asia/Tokyo")
        mock_adapter.parsed_info_to_parsed_activity.assert_called_once_with({"activity": "gpx"})

    @patch("modules.activities.activity_file_import.registry.adapter")
    @patch("modules.activities.activity_file_import.registry.tcx_utils")
    def test_tcx_adapter_forwards_the_fallback_timezone(self, mock_tcx, mock_adapter):
        mock_tcx.parse_tcx_file.return_value = {"activity": "tcx"}
        mock_adapter.parsed_info_to_parsed_activity.return_value = "parsed-tcx"
        parser = registry.get_parser(".tcx")

        result = parser("/f.tcx", 7, "Name", "Asia/Tokyo")

        assert result.activities == ["parsed-tcx"]
        mock_tcx.parse_tcx_file.assert_called_once_with("/f.tcx", 7, "Name", "Asia/Tokyo")

    @patch("modules.activities.activity_file_import.registry.gpx_utils")
    def test_fallback_timezone_is_optional(self, mock_gpx):
        mock_gpx.parse_gpx_file.return_value = {"activity": "gpx"}
        parser = registry.get_parser(".gpx")
        parser("/f.gpx", 7)
        mock_gpx.parse_gpx_file.assert_called_once_with("/f.gpx", 7, None, None)

    @patch("modules.activities.activity_file_import.registry.adapter")
    @patch("modules.activities.activity_file_import.registry.fit_utils")
    def test_fit_adapter_runs_the_split_and_build_stages(self, mock_fit, mock_adapter):
        # FIT's first stage is owner- and timezone-agnostic; the owner and the
        # fallback timezone apply in the second stage, which the adapter runs so
        # that callers never see the difference between formats.
        mock_fit.parse_fit_file.return_value = {"exercise_titles": ["title"]}
        mock_fit.split_records_by_activity.return_value = ["session-a", "session-b"]
        mock_fit.create_activity_objects.return_value = ["info-a", "info-b"]
        mock_adapter.parsed_info_to_parsed_activity.side_effect = lambda info: f"parsed-{info}"
        parser = registry.get_parser(".fit")

        result = parser("/f.fit", 7, "Name", "Asia/Tokyo")

        assert result.activities == ["parsed-info-a", "parsed-info-b"]
        assert result.components == {"exercise_titles": ["title"]}
        mock_fit.parse_fit_file.assert_called_once_with("/f.fit", "Name")
        mock_fit.split_records_by_activity.assert_called_once_with({"exercise_titles": ["title"]})
        mock_fit.create_activity_objects.assert_called_once_with(["session-a", "session-b"], 7, "Asia/Tokyo")

    @patch("modules.activities.activity_file_import.registry.adapter")
    @patch("modules.activities.activity_file_import.registry.fit_utils")
    def test_multi_activity_fit_is_not_special_to_the_caller(self, mock_fit, mock_adapter):
        # The whole point of ParsedFile: one file can hold several activities and
        # the ingestion core does not branch on the extension to find out.
        mock_fit.parse_fit_file.return_value = {}
        mock_fit.split_records_by_activity.return_value = ["s1", "s2", "s3"]
        mock_fit.create_activity_objects.return_value = ["i1", "i2", "i3"]
        mock_adapter.parsed_info_to_parsed_activity.side_effect = lambda info: info

        result = registry.get_parser(".fit")("/f.fit", 7)

        assert result.activities == ["i1", "i2", "i3"]
        assert result.components == {"exercise_titles": None}
