"""Tests for the ingestion pipeline (validate -> parse -> enrich -> store -> retain).

Covers ``parse_file``'s registry dispatch and error contract. The generic file
plumbing the pipeline used to own — gzip expansion, content hashing, artifact
cleanup — now lives in ``core.file_uploads`` and is tested there.
"""

from unittest.mock import patch

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity.contracts as activities_contracts
import modules.activities.activity_ingestion.pipeline as pipeline
import modules.activities.activity_ingestion.sources as sources


class TestParseFile:
    @patch("modules.activities.activity_file_import.registry.adapter")
    @patch("modules.activities.activity_file_import.registry.gpx_utils")
    def test_parse_gpx(self, mock_gpx, mock_adapter):
        mock_gpx.parse_gpx_file.return_value = {"activity": "data"}
        mock_adapter.parsed_info_to_parsed_activity.return_value = "parsed"

        result = pipeline.parse_file(
            token_user_id=1,
            file_extension=".gpx",
            filename="/path/to/file.gpx",
        )

        assert result.activities == ["parsed"]

    @patch("modules.activities.activity_file_import.registry.adapter")
    @patch("modules.activities.activity_file_import.registry.tcx_utils")
    def test_parse_tcx(self, mock_tcx, mock_adapter):
        mock_tcx.parse_tcx_file.return_value = {"activity": "tcx_data"}
        mock_adapter.parsed_info_to_parsed_activity.return_value = "parsed"

        result = pipeline.parse_file(
            token_user_id=1,
            file_extension=".tcx",
            filename="/path/to/file.tcx",
        )

        assert result.activities == ["parsed"]

    @patch("modules.activities.activity_file_import.registry.adapter")
    @patch("modules.activities.activity_file_import.registry.fit_utils")
    def test_parse_fit_returns_every_activity_in_the_file(self, mock_fit, mock_adapter):
        # The pipeline no longer knows that .fit can hold several activities.
        mock_fit.parse_fit_file.return_value = {}
        mock_fit.split_records_by_activity.return_value = ["s1", "s2"]
        mock_fit.create_activity_objects.return_value = ["i1", "i2"]
        mock_adapter.parsed_info_to_parsed_activity.side_effect = lambda info: info

        result = pipeline.parse_file(
            token_user_id=1,
            file_extension=".fit",
            filename="/path/to/file.fit",
        )

        assert result.activities == ["i1", "i2"]

    def test_raises_on_unsupported_extension(self):
        with pytest.raises(core_exceptions.UnsupportedFormatError) as exc:
            pipeline.parse_file(
                token_user_id=1,
                file_extension=".xyz",
                filename="/path/to/file.xyz",
            )
        assert exc.value.status_code == 406

    def test_returns_none_for_bulk_import_init(self):
        result = pipeline.parse_file(
            token_user_id=1,
            file_extension=".py",
            filename="bulk_import/__init__.py",
        )
        assert result is None


class TestParseFileError:
    """Exception handler in parse_file."""

    @patch("modules.activities.activity_file_import.registry.gpx_utils")
    def test_raises_500_on_parse_error(self, mock_gpx):
        mock_gpx.parse_gpx_file.side_effect = ValueError("bad data")

        with pytest.raises(core_exceptions.ProcessingError) as exc:
            pipeline.parse_file(
                token_user_id=1,
                file_extension=".gpx",
                filename="/path/to/file.gpx",
            )
        assert exc.value.status_code == 500


class TestRetainSourceFile:
    def test_stores_one_copy_per_activity_then_removes_the_input(self, tmp_path):
        source = tmp_path / "ride.gpx"
        source.write_bytes(b"<gpx/>")

        with (
            patch.object(pipeline.file_storage_integration, "store_activity_file_for_ids") as store,
            patch.object(pipeline.platform_runtime, "get_active_platform"),
        ):
            pipeline._retain_source_file(str(source), ".gpx", [4, 5])

        assert store.call_args.args[0] == [4, 5]
        assert store.call_args.args[2] == b"<gpx/>"
        assert not source.exists()

    def test_removes_the_input_even_when_nothing_was_created(self, tmp_path):
        source = tmp_path / "ride.gpx"
        source.write_bytes(b"<gpx/>")

        with patch.object(pipeline.file_storage_integration, "store_activity_file_for_ids") as store:
            pipeline._retain_source_file(str(source), ".gpx", [])

        store.assert_not_called()
        assert not source.exists()


class TestParsedFileContract:
    def test_defaults_to_no_activities(self):
        assert activities_contracts.ParsedFile().activities == []
        assert activities_contracts.ParsedFile().exercise_titles is None


class TestStoreActivitiesFromFile:
    def test_a_file_that_yields_no_activities_is_still_cleaned_up(self, tmp_path):
        # A parse that produces nothing must not leave the staged file behind for
        # the next import run to pick up again.
        source = tmp_path / "empty.fit"
        source.write_bytes(b"\x00")

        with (
            patch.object(pipeline.users_integration_service, "get_user"),
            patch.object(pipeline.users_integration_service, "get_privacy_settings"),
            patch.object(pipeline, "parse_file", return_value=activities_contracts.ParsedFile()),
            patch.object(pipeline.core_file_uploads, "sha256_file", return_value="hash"),
            patch.object(pipeline.file_storage_integration, "store_activity_file_for_ids") as store,
        ):
            result = pipeline.store_activities_from_file(
                1,
                str(source),
                ".fit",
                "empty.fit",
                "db",
                source=sources.UploadSource(),
            )

        assert result == []
        store.assert_not_called()
        assert not source.exists()

    def test_the_marker_file_returns_none_without_touching_storage(self, tmp_path):
        source = tmp_path / "keep.gpx"
        source.write_bytes(b"<gpx/>")

        with (
            patch.object(pipeline.users_integration_service, "get_user"),
            patch.object(pipeline.users_integration_service, "get_privacy_settings"),
            patch.object(pipeline, "parse_file", return_value=None),
        ):
            result = pipeline.store_activities_from_file(
                1,
                str(source),
                ".gpx",
                "keep.gpx",
                "db",
                source=sources.UploadSource(),
            )

        assert result is None
        assert source.exists()
