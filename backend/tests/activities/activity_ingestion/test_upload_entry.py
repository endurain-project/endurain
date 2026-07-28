"""Tests for the split upload entry: staging in the request, parsing in the job."""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.upload_entry as upload_entry


def _file(filename) -> MagicMock:
    file = MagicMock()
    file.filename = filename
    return file


class TestStageUploadedActivityFile:
    def test_streams_to_the_staging_directory_under_a_server_name(self):
        with patch.object(
            upload_entry.core_file_uploads, "save_validated_upload_sync", return_value="/s/x.gpx"
        ) as save:
            result = upload_entry.stage_uploaded_activity_file(_file("../../etc/passwd.gpx"))

        assert result == "/s/x.gpx"
        assert save.call_args.kwargs["upload_dir"] == upload_entry.core_config.FILES_UPLOAD_STAGING_DIR
        # The client filename never reaches the filesystem.
        assert save.call_args.kwargs["filename"].endswith(".gpx")
        assert "passwd" not in save.call_args.kwargs["filename"]
        assert "/" not in save.call_args.kwargs["filename"]

    def test_rejects_a_missing_filename(self):
        with pytest.raises(core_exceptions.InvalidInputError):
            upload_entry.stage_uploaded_activity_file(_file(None))

    def test_rejects_an_unsupported_extension_before_writing_anything(self):
        with (
            patch.object(upload_entry.core_file_uploads, "save_validated_upload_sync") as save,
            pytest.raises(core_exceptions.UnsupportedFormatError),
        ):
            upload_entry.stage_uploaded_activity_file(_file("notes.txt"))

        save.assert_not_called()

    def test_a_gz_upload_is_validated_as_gzip(self):
        with patch.object(upload_entry.core_file_uploads, "save_validated_upload_sync", return_value="/s/x.gz") as save:
            upload_entry.stage_uploaded_activity_file(_file("ride.gpx.gz"))

        assert save.call_args.kwargs["kind"] == upload_entry.core_file_uploads.UploadKind.GZIP


class TestProcessStagedUpload:
    def test_confines_the_path_to_the_staging_directory(self):
        """A tampered stored path must not make the parser read an arbitrary file."""
        db = MagicMock()
        with (
            patch.object(
                upload_entry.core_file_uploads,
                "ensure_within",
                side_effect=ValueError("escapes the staging dir"),
            ),
            pytest.raises(ValueError),
        ):
            upload_entry.process_staged_upload(7, "/etc/passwd", db)

    def test_parses_and_returns_the_created_activities(self):
        db = MagicMock()
        with (
            patch.object(upload_entry.core_file_uploads, "ensure_within", side_effect=lambda p, base: p),
            patch.object(upload_entry.pipeline, "store_activities_from_file", return_value=["activity"]) as store,
        ):
            result = upload_entry.process_staged_upload(7, "/s/x.gpx", db)

        assert result == ["activity"]
        assert store.call_args.args[0] == 7
        assert store.call_args.args[3] == "x.gpx"

    def test_removes_the_staged_file_when_nothing_parsed(self):
        db = MagicMock()
        with (
            patch.object(upload_entry.core_file_uploads, "ensure_within", side_effect=lambda p, base: p),
            patch.object(upload_entry.pipeline, "store_activities_from_file", return_value=None),
            patch.object(upload_entry.core_file_uploads, "remove_files") as remove,
        ):
            result = upload_entry.process_staged_upload(7, "/s/x.gpx", db)

        assert result is None
        remove.assert_called_once_with(["/s/x.gpx"])

    def test_cleans_up_and_converts_unexpected_failures(self):
        db = MagicMock()
        with (
            patch.object(upload_entry.core_file_uploads, "ensure_within", side_effect=lambda p, base: p),
            patch.object(upload_entry.pipeline, "store_activities_from_file", side_effect=OSError("disk gone")),
            patch.object(upload_entry.core_file_uploads, "remove_files") as remove,
            pytest.raises(core_exceptions.ProcessingError),
        ):
            upload_entry.process_staged_upload(7, "/s/x.gpx", db)

        remove.assert_called_once_with(["/s/x.gpx"])

    def test_a_gz_that_decompresses_to_an_unsupported_payload_is_rejected(self):
        db = MagicMock()
        with (
            patch.object(upload_entry.core_file_uploads, "ensure_within", side_effect=lambda p, base: p),
            patch.object(upload_entry.core_file_uploads, "decompress_gzip", return_value=("/s/x.exe", ".exe")),
            patch.object(upload_entry.core_file_uploads, "remove_files"),
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            upload_entry.process_staged_upload(7, "/s/x.gz", db)
