"""Tests for the ingestion pipeline (validate -> parse -> enrich -> store -> retain).

Covers ``parse_file``'s registry dispatch and error contract. The generic file
plumbing the pipeline used to own — gzip expansion, content hashing, artifact
cleanup — now lives in ``core.file_uploads`` and is tested there.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity_ingestion.contracts as sources
import modules.activities.activity_ingestion.pipeline_service as pipeline


class TestParseFile:
    @patch("modules.activities.activity_file_import.parser_registry.activity_file_import_adapter")
    @patch("modules.activities.activity_file_import.parser_registry.activity_file_import_gpx_utils")
    def test_parse_gpx(self, mock_gpx, mock_adapter):
        mock_gpx.parse_gpx_file.return_value = {"activity": "data"}
        mock_adapter.parsed_info_to_parsed_activity.return_value = "parsed"

        result = pipeline.parse_file(
            token_user_id=1,
            file_extension=".gpx",
            filename="/path/to/file.gpx",
        )

        assert result.activities == ["parsed"]

    @patch("modules.activities.activity_file_import.parser_registry.activity_file_import_adapter")
    @patch("modules.activities.activity_file_import.parser_registry.activity_file_import_tcx_utils")
    def test_parse_tcx(self, mock_tcx, mock_adapter):
        mock_tcx.parse_tcx_file.return_value = {"activity": "tcx_data"}
        mock_adapter.parsed_info_to_parsed_activity.return_value = "parsed"

        result = pipeline.parse_file(
            token_user_id=1,
            file_extension=".tcx",
            filename="/path/to/file.tcx",
        )

        assert result.activities == ["parsed"]

    @patch("modules.activities.activity_file_import.parser_registry.activity_file_import_adapter")
    @patch("modules.activities.activity_file_import.parser_registry.activity_file_import_fit_utils")
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

    @patch("modules.activities.activity_file_import.parser_registry.activity_file_import_gpx_utils")
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

        storage = MagicMock()

        with patch.object(pipeline.activity_file_storage_integration, "store_activity_file_for_ids") as store:
            pipeline._retain_source_file(str(source), ".gpx", [4, 5], storage)

        assert store.call_args.args[0] == [4, 5]
        assert store.call_args.args[2] == b"<gpx/>"
        assert store.call_args.args[3] is storage
        assert not source.exists()

    def test_removes_the_input_even_when_nothing_was_created(self, tmp_path):
        source = tmp_path / "ride.gpx"
        source.write_bytes(b"<gpx/>")

        with patch.object(pipeline.activity_file_storage_integration, "store_activity_file_for_ids") as store:
            pipeline._retain_source_file(str(source), ".gpx", [], MagicMock())

        store.assert_not_called()
        assert not source.exists()


class TestParsedFileContract:
    def test_defaults_to_no_activities(self):
        assert activity_contracts.ParsedFile().activities == []
        assert activity_contracts.ParsedFile().components == {}


class TestStoreActivitiesFromFile:
    def test_persists_file_components_through_the_registry(self, tmp_path):
        source_file = tmp_path / "empty.fit"
        source_file.write_bytes(b"\x00")
        contributor = MagicMock(key="exercise_titles")
        db = MagicMock()

        with (
            patch.object(pipeline.users_integration, "get_user"),
            patch.object(pipeline.users_integration, "get_privacy_settings"),
            patch.object(
                pipeline,
                "parse_file",
                return_value=activity_contracts.ParsedFile(
                    components={"exercise_titles": [{"exercise_name": "Press"}]}
                ),
            ),
            patch.object(
                pipeline.activities_contributor_registry,
                "get_file_ingestion_contributor",
                return_value=contributor,
            ) as get_contributor,
            patch.object(pipeline.core_file_uploads, "sha256_file", return_value="hash"),
        ):
            result = pipeline.store_activities_from_file(
                1,
                str(source_file),
                ".fit",
                "empty.fit",
                db,
                source=sources.UploadSource(),
                storage=MagicMock(),
            )

        assert result == []
        get_contributor.assert_called_once_with("exercise_titles")
        contributor.persist.assert_called_once_with([{"exercise_name": "Press"}], db)
        # One commit ends the read transaction before the parse, one persists the
        # file-scoped reference data ahead of the activity unit.
        assert db.commit.call_count == 2

    def test_unknown_file_component_fails_closed(self, tmp_path):
        source_file = tmp_path / "unknown.fit"
        source_file.write_bytes(b"\x00")

        with (
            patch.object(pipeline.users_integration, "get_user"),
            patch.object(pipeline.users_integration, "get_privacy_settings"),
            patch.object(
                pipeline,
                "parse_file",
                return_value=activity_contracts.ParsedFile(components={"unknown": [{}]}),
            ),
            pytest.raises(core_exceptions.ProcessingError) as raised,
        ):
            pipeline.store_activities_from_file(
                1,
                str(source_file),
                ".fit",
                "unknown.fit",
                MagicMock(),
                source=sources.UploadSource(),
                storage=MagicMock(),
            )

        assert "unknown" not in raised.value.detail

    def test_a_file_that_yields_no_activities_is_still_cleaned_up(self, tmp_path):
        # A parse that produces nothing must not leave the staged file behind for
        # the next import run to pick up again.
        source = tmp_path / "empty.fit"
        source.write_bytes(b"\x00")

        with (
            patch.object(pipeline.users_integration, "get_user"),
            patch.object(pipeline.users_integration, "get_privacy_settings"),
            patch.object(pipeline, "parse_file", return_value=activity_contracts.ParsedFile()),
            patch.object(pipeline.core_file_uploads, "sha256_file", return_value="hash"),
            patch.object(pipeline.activity_file_storage_integration, "store_activity_file_for_ids") as store,
        ):
            result = pipeline.store_activities_from_file(
                1,
                str(source),
                ".fit",
                "empty.fit",
                MagicMock(),
                source=sources.UploadSource(),
                storage=MagicMock(),
            )

        assert result == []
        store.assert_not_called()
        assert not source.exists()

    def test_the_marker_file_returns_none_without_touching_storage(self, tmp_path):
        source = tmp_path / "keep.gpx"
        source.write_bytes(b"<gpx/>")

        with (
            patch.object(pipeline.users_integration, "get_user"),
            patch.object(pipeline.users_integration, "get_privacy_settings"),
            patch.object(pipeline, "parse_file", return_value=None),
        ):
            result = pipeline.store_activities_from_file(
                1,
                str(source),
                ".gpx",
                "keep.gpx",
                MagicMock(),
                source=sources.UploadSource(),
                storage=MagicMock(),
            )

        assert result is None
        assert source.exists()


class TestParseFileTimezoneFallback:
    """The parsers are pure, so the pipeline applies the server timezone."""

    def test_uses_the_server_timezone_when_the_owner_has_none(self):
        from unittest.mock import MagicMock, patch

        import core.config as core_config
        import modules.activities.activity_ingestion.pipeline_service as pipeline_service

        parser = MagicMock(return_value="parsed")
        with patch.object(pipeline_service.activity_file_import_integration, "get_parser", return_value=parser):
            pipeline_service.parse_file(1, ".gpx", "/f.gpx")

        assert parser.call_args.args[3] == core_config.settings.TZ


class TestGzipArtifacts:
    """A ``.gz`` import owns two files: the archive and its decompressed temp copy."""

    @staticmethod
    def _archive(tmp_path):
        import gzip

        archive = tmp_path / "ride.gpx.gz"
        archive.write_bytes(gzip.compress(b"<gpx/>"))
        return archive

    @staticmethod
    def _run(archive, *, store):
        seen: list[str] = []

        def _store(_user_id, file_path, *_args, **_kwargs):
            seen.append(file_path)
            return store()

        with (
            patch.object(pipeline.core_file_uploads, "validate_local_file_sync"),
            patch.object(pipeline, "store_activities_from_file", side_effect=_store),
        ):
            try:
                result = pipeline.validate_prepare_and_store_file(
                    3,
                    str(archive),
                    MagicMock(),
                    source=sources.BulkImportSource(import_initiated_time="2026-07-21T00:00:00"),
                    storage=MagicMock(),
                )
            except Exception as err:
                return None, err, seen
        return result, None, seen

    def test_a_failed_import_removes_the_temp_copy_and_keeps_the_archive(self, tmp_path):
        """The archive is what the caller moves to the error directory."""
        archive = self._archive(tmp_path)

        def _fail():
            raise RuntimeError("parser")

        _result, error, seen = self._run(archive, store=_fail)

        assert isinstance(error, RuntimeError)
        assert archive.exists()
        assert len(seen) == 1
        assert not os.path.exists(seen[0])

    def test_a_successful_import_consumes_the_archive_and_the_temp_copy(self, tmp_path):
        archive = self._archive(tmp_path)

        result, error, seen = self._run(archive, store=lambda: ["activity"])

        assert error is None
        assert result == ["activity"]
        assert not archive.exists()
        assert not os.path.exists(seen[0])

    def test_an_unsupported_inner_payload_leaves_no_temp_copy(self, tmp_path):
        import gzip

        archive = tmp_path / "ride.exe.gz"
        archive.write_bytes(gzip.compress(b"MZ"))
        temp_paths: list[str] = []
        real_decompress = pipeline.core_file_uploads.decompress_gzip

        def _record(path):
            temp_path, extension = real_decompress(path)
            temp_paths.append(temp_path)
            return temp_path, extension

        with (
            patch.object(pipeline.core_file_uploads, "validate_local_file_sync"),
            patch.object(pipeline.core_file_uploads, "decompress_gzip", side_effect=_record),
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            pipeline.validate_prepare_and_store_file(
                3,
                str(archive),
                MagicMock(),
                source=sources.BulkImportSource(import_initiated_time="2026-07-21T00:00:00"),
                storage=MagicMock(),
            )

        assert archive.exists()
        assert len(temp_paths) == 1
        assert not os.path.exists(temp_paths[0])
