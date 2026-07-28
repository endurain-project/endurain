"""Tests for the split upload entry: staging in the request, parsing in the job."""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.upload_entry as upload_entry


def _file(filename) -> MagicMock:
    file = MagicMock()
    file.filename = filename
    return file


def _platform() -> MagicMock:
    """A platform whose StorageProvider is a stub."""
    platform = MagicMock()
    platform.storage = MagicMock()
    return platform


class TestStageUploadedActivityFile:
    def test_hands_the_upload_to_storage_under_a_server_generated_key(self):
        platform = _platform()
        with (
            patch.object(upload_entry.platform_runtime, "get_active_platform", return_value=platform),
            patch.object(
                upload_entry.core_file_uploads,
                "save_validated_upload_sync",
                return_value="/incoming/x.gpx",
            ) as save,
            patch.object(upload_entry.Path, "read_bytes", return_value=b"<gpx/>"),
            patch.object(upload_entry.core_file_uploads, "remove_files") as remove,
        ):
            key = upload_entry.stage_uploaded_activity_file(_file("../../etc/passwd.gpx"))

        # The client filename reaches neither the filesystem nor the storage key.
        assert key.endswith(".gpx")
        assert "passwd" not in key
        assert "/" not in key
        # Streamed to the incoming dir, which must differ from the storage area
        # or the local backend would be copying a file onto itself.
        assert save.call_args.kwargs["upload_dir"] == upload_entry.core_config.FILES_UPLOAD_INCOMING_DIR
        platform.storage.save.assert_called_once_with(upload_entry.UPLOAD_STAGING_STORAGE_AREA, key, b"<gpx/>")
        # The local copy is not left behind once storage owns the bytes.
        remove.assert_called_once_with(["/incoming/x.gpx"])

    def test_removes_the_incoming_file_when_storage_fails(self):
        platform = _platform()
        platform.storage.save.side_effect = RuntimeError("bucket down")
        with (
            patch.object(upload_entry.platform_runtime, "get_active_platform", return_value=platform),
            patch.object(
                upload_entry.core_file_uploads,
                "save_validated_upload_sync",
                return_value="/incoming/x.gpx",
            ),
            patch.object(upload_entry.Path, "read_bytes", return_value=b"<gpx/>"),
            patch.object(upload_entry.core_file_uploads, "remove_files") as remove,
            pytest.raises(RuntimeError),
        ):
            upload_entry.stage_uploaded_activity_file(_file("ride.gpx"))

        remove.assert_called_once_with(["/incoming/x.gpx"])

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
        platform = _platform()
        with (
            patch.object(upload_entry.platform_runtime, "get_active_platform", return_value=platform),
            patch.object(
                upload_entry.core_file_uploads,
                "save_validated_upload_sync",
                return_value="/incoming/x.gz",
            ) as save,
            patch.object(upload_entry.Path, "read_bytes", return_value=b"\x1f\x8b"),
            patch.object(upload_entry.core_file_uploads, "remove_files"),
        ):
            upload_entry.stage_uploaded_activity_file(_file("ride.gpx.gz"))

        assert save.call_args.kwargs["kind"] == upload_entry.core_file_uploads.UploadKind.GZIP


class TestProcessStagedUpload:
    def test_materializes_the_blob_and_parses_it(self):
        """The bytes come from storage, so any worker node can run the parse."""
        db = MagicMock()
        platform = _platform()
        platform.storage.get.return_value = b"<gpx/>"
        with (
            patch.object(upload_entry.platform_runtime, "get_active_platform", return_value=platform),
            patch.object(upload_entry.pipeline, "store_activities_from_file", return_value=["activity"]) as store,
            patch.object(upload_entry.core_file_uploads, "remove_files"),
        ):
            result = upload_entry.process_staged_upload(7, "abc.gpx", db)

        assert result == ["activity"]
        platform.storage.get.assert_called_once_with(upload_entry.UPLOAD_STAGING_STORAGE_AREA, "abc.gpx")
        assert store.call_args.args[0] == 7
        assert store.call_args.args[3] == "abc.gpx"
        # Consumed on success.
        platform.storage.delete.assert_called_once_with(upload_entry.UPLOAD_STAGING_STORAGE_AREA, "abc.gpx")

    def test_rejects_a_blob_that_is_gone(self):
        db = MagicMock()
        platform = _platform()
        platform.storage.get.return_value = None
        with (
            patch.object(upload_entry.platform_runtime, "get_active_platform", return_value=platform),
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            upload_entry.process_staged_upload(7, "abc.gpx", db)

    def test_discards_the_blob_when_nothing_parsed(self):
        db = MagicMock()
        platform = _platform()
        platform.storage.get.return_value = b"<gpx/>"
        with (
            patch.object(upload_entry.platform_runtime, "get_active_platform", return_value=platform),
            patch.object(upload_entry.pipeline, "store_activities_from_file", return_value=None),
            patch.object(upload_entry.core_file_uploads, "remove_files"),
        ):
            result = upload_entry.process_staged_upload(7, "abc.gpx", db)

        assert result is None
        platform.storage.delete.assert_called_once_with(upload_entry.UPLOAD_STAGING_STORAGE_AREA, "abc.gpx")

    def test_keeps_the_blob_when_the_failure_may_be_transient(self):
        """A retry has to have something left to read."""
        db = MagicMock()
        platform = _platform()
        platform.storage.get.return_value = b"<gpx/>"
        with (
            patch.object(upload_entry.platform_runtime, "get_active_platform", return_value=platform),
            patch.object(upload_entry.pipeline, "store_activities_from_file", side_effect=OSError("disk gone")),
            patch.object(upload_entry.core_file_uploads, "remove_files"),
            pytest.raises(core_exceptions.ProcessingError),
        ):
            upload_entry.process_staged_upload(7, "abc.gpx", db)

        platform.storage.delete.assert_not_called()

    def test_a_gz_that_decompresses_to_an_unsupported_payload_is_rejected(self):
        db = MagicMock()
        platform = _platform()
        platform.storage.get.return_value = b"\x1f\x8b"
        with (
            patch.object(upload_entry.platform_runtime, "get_active_platform", return_value=platform),
            patch.object(upload_entry.core_file_uploads, "decompress_gzip", return_value=("/tmp/x.exe", ".exe")),
            patch.object(upload_entry.core_file_uploads, "remove_files"),
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            upload_entry.process_staged_upload(7, "abc.gz", db)

    def test_removes_the_working_directory_on_every_path(self):
        db = MagicMock()
        platform = _platform()
        platform.storage.get.return_value = b"<gpx/>"
        with (
            patch.object(upload_entry.platform_runtime, "get_active_platform", return_value=platform),
            patch.object(upload_entry.pipeline, "store_activities_from_file", side_effect=OSError("boom")),
            patch.object(upload_entry.core_file_uploads, "remove_files"),
            patch.object(upload_entry.shutil, "rmtree") as rmtree,
            pytest.raises(core_exceptions.ProcessingError),
        ):
            upload_entry.process_staged_upload(7, "abc.gpx", db)

        rmtree.assert_called_once()


class TestDiscardStagedUpload:
    def test_deletes_the_blob(self):
        platform = _platform()
        with patch.object(upload_entry.platform_runtime, "get_active_platform", return_value=platform):
            upload_entry.discard_staged_upload("abc.gpx")
        platform.storage.delete.assert_called_once_with(upload_entry.UPLOAD_STAGING_STORAGE_AREA, "abc.gpx")

    def test_a_storage_failure_never_propagates(self):
        """Cleanup must not turn a finished import into a failed one."""
        platform = _platform()
        platform.storage.delete.side_effect = RuntimeError("bucket down")
        with patch.object(upload_entry.platform_runtime, "get_active_platform", return_value=platform):
            upload_entry.discard_staged_upload("abc.gpx")
