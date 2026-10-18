"""Tests for the split upload entry: staging in the request, parsing in the job."""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from jasil.backends.storage_local import LocalStorage

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.upload_entry_service as upload_entry_service


def _platform() -> MagicMock:
    """A platform whose StorageProvider is a stub."""
    platform = MagicMock()
    platform.storage = MagicMock()
    return platform


def _blob(platform: MagicMock, data: bytes | None) -> None:
    """Make the stub storage serve ``data`` from ``open_stream``, or report the object missing."""
    if data is None:
        platform.storage.open_stream.side_effect = FileNotFoundError("missing")
    else:
        platform.storage.open_stream.side_effect = lambda *_a, **_k: io.BytesIO(data)


@pytest.fixture
def local_storage(tmp_path) -> LocalStorage:
    return LocalStorage(base_dir=str(tmp_path / "storage"), url_prefix="/files")


class TestReceiveUpload:
    def test_streams_to_incoming_under_a_server_generated_key_and_fingerprints_it(self):
        save = MagicMock(return_value="/incoming/x.gpx")
        with patch.object(upload_entry_service.core_file_uploads, "sha256_file", return_value="deadbeef"):
            received = upload_entry_service.receive_upload("../../etc/passwd.gpx", save, fingerprint=True)

        # The client filename reaches neither the filesystem nor the storage key.
        assert received.storage_key.endswith(".gpx")
        assert "passwd" not in received.storage_key
        assert "/" not in received.storage_key
        # Streamed to the incoming dir, which must differ from the storage area
        # or the local backend would be copying a file onto itself.
        assert save.call_args.kwargs["upload_dir"] == upload_entry_service.core_config.FILES_UPLOAD_INCOMING_DIR
        # Fingerprinted here, not after storing, so an idempotent replay can be
        # verified without paying for the storage write.
        assert received.fingerprint == "deadbeef"

    def test_a_failed_fingerprint_removes_the_incoming_file(self):
        """The caller never gets the path on failure, so nothing else would clean it up."""
        save = MagicMock(return_value="/incoming/x.gpx")
        with (
            patch.object(upload_entry_service.core_file_uploads, "sha256_file", side_effect=OSError("disk")),
            patch.object(upload_entry_service.core_file_uploads, "remove_files") as remove_files,
            pytest.raises(OSError),
        ):
            upload_entry_service.receive_upload("ride.gpx", save, fingerprint=True)

        remove_files.assert_called_once_with(["/incoming/x.gpx"])

    def test_skips_the_hash_when_no_idempotency_key_was_sent(self):
        """Nothing reads the fingerprint without a key, so it is not worth a pass over the file."""
        with patch.object(upload_entry_service.core_file_uploads, "sha256_file") as hash_bytes:
            received = upload_entry_service.receive_upload("ride.gpx", MagicMock(return_value="/incoming/x.gpx"))

        assert received.fingerprint is None
        hash_bytes.assert_not_called()

    def test_the_file_is_not_read_into_memory(self):
        """An activity file is up to 200 MiB; only the fingerprint pass touches it, in chunks."""
        with patch("pathlib.Path.read_bytes") as read_bytes:
            upload_entry_service.receive_upload("ride.gpx", MagicMock(return_value="/incoming/x.gpx"))

        read_bytes.assert_not_called()

    def test_rejects_a_missing_filename(self):
        with pytest.raises(core_exceptions.InvalidInputError):
            upload_entry_service.receive_upload(None, MagicMock())

    def test_rejects_an_unsupported_extension_before_writing_anything(self):
        save = MagicMock()
        with pytest.raises(core_exceptions.UnsupportedFormatError):
            upload_entry_service.receive_upload("notes.txt", save)

        save.assert_not_called()

    def test_a_gz_upload_is_validated_as_gzip(self):
        save = MagicMock(return_value="/incoming/x.gz")
        upload_entry_service.receive_upload("ride.gpx.gz", save)

        assert save.call_args.kwargs["kind"] == upload_entry_service.core_file_uploads.UploadKind.GZIP


class TestStoreReceivedUpload:
    @pytest.fixture(autouse=True)
    def _incoming(self, tmp_path):
        self.incoming = tmp_path / "x.gpx"
        self.incoming.write_bytes(b"<gpx/>")

    def _received(self) -> upload_entry_service.ReceivedUpload:
        return upload_entry_service.ReceivedUpload(
            incoming_path=str(self.incoming), storage_key="abc.gpx", fingerprint="deadbeef"
        )

    def test_hands_the_bytes_to_storage_and_drops_the_local_copy(self):
        platform = _platform()
        streamed: list[bytes] = []
        platform.storage.save_stream.side_effect = lambda _area, _key, source: streamed.append(source.read())
        with patch.object(upload_entry_service.core_file_uploads, "remove_files") as remove:
            key = upload_entry_service.store_received_upload(self._received(), platform.storage)

        assert key == "abc.gpx"
        assert platform.storage.save_stream.call_args.args[:2] == (
            upload_entry_service.UPLOAD_STAGING_STORAGE_AREA,
            "upload_staging/abc.gpx",
        )
        # Streamed from the file, never handed over as a whole in-memory buffer.
        assert streamed == [b"<gpx/>"]
        platform.storage.save.assert_not_called()
        remove.assert_called_once_with([str(self.incoming)])

    def test_removes_the_incoming_file_when_storage_fails(self):
        platform = _platform()
        platform.storage.save_stream.side_effect = RuntimeError("bucket down")
        with (
            patch.object(upload_entry_service.core_file_uploads, "remove_files") as remove,
            pytest.raises(RuntimeError),
        ):
            upload_entry_service.store_received_upload(self._received(), platform.storage)

        remove.assert_called_once_with([str(self.incoming)])

    def test_discarding_removes_the_incoming_file(self):
        with patch.object(upload_entry_service.core_file_uploads, "remove_files") as remove:
            upload_entry_service.discard_received_upload(self._received())

        remove.assert_called_once_with([str(self.incoming)])


class TestProcessStagedUpload:
    def test_materializes_the_blob_and_parses_it(self):
        """The bytes come from storage, so any worker node can run the parse."""
        db = MagicMock()
        platform = _platform()
        _blob(platform, b"<gpx/>")
        with (
            patch.object(
                upload_entry_service.activity_ingestion_pipeline_service,
                "store_activities_from_file",
                return_value=["activity"],
            ) as store,
            patch.object(upload_entry_service.core_file_uploads, "remove_files"),
        ):
            result = upload_entry_service.process_staged_upload(7, "abc.gpx", platform.storage, db)

        assert result == ["activity"]
        platform.storage.open_stream.assert_called_once_with(
            upload_entry_service.UPLOAD_STAGING_STORAGE_AREA,
            "upload_staging/abc.gpx",
        )
        assert store.call_args.args[0] == 7
        assert store.call_args.args[3] == "abc.gpx"
        # Left for the caller, which removes it only once the outcome is committed.
        platform.storage.delete.assert_not_called()

    def test_rejects_a_blob_that_is_gone(self):
        db = MagicMock()
        platform = _platform()
        _blob(platform, None)
        with (
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            upload_entry_service.process_staged_upload(7, "abc.gpx", platform.storage, db)

    def test_keeps_the_blob_when_nothing_parsed(self):
        db = MagicMock()
        platform = _platform()
        _blob(platform, b"<gpx/>")
        with (
            patch.object(
                upload_entry_service.activity_ingestion_pipeline_service,
                "store_activities_from_file",
                return_value=None,
            ),
            patch.object(upload_entry_service.core_file_uploads, "remove_files"),
        ):
            result = upload_entry_service.process_staged_upload(7, "abc.gpx", platform.storage, db)

        assert result is None
        platform.storage.delete.assert_not_called()

    def test_keeps_the_blob_when_the_failure_may_be_transient(self):
        """A retry has to have something left to read."""
        db = MagicMock()
        platform = _platform()
        _blob(platform, b"<gpx/>")
        with (
            patch.object(
                upload_entry_service.activity_ingestion_pipeline_service,
                "store_activities_from_file",
                side_effect=OSError("disk gone"),
            ),
            patch.object(upload_entry_service.core_file_uploads, "remove_files"),
            pytest.raises(core_exceptions.ProcessingError),
        ):
            upload_entry_service.process_staged_upload(7, "abc.gpx", platform.storage, db)

        platform.storage.delete.assert_not_called()

    def test_a_database_error_propagates_untranslated_and_keeps_the_blob(self):
        """The job runner retries on a raw database error; translating it hid its type."""
        from sqlalchemy.exc import SQLAlchemyError

        db = MagicMock()
        platform = _platform()
        _blob(platform, b"<gpx/>")
        with (
            patch.object(
                upload_entry_service.activity_ingestion_pipeline_service,
                "store_activities_from_file",
                side_effect=SQLAlchemyError("down"),
            ),
            patch.object(upload_entry_service.core_file_uploads, "remove_files"),
            pytest.raises(SQLAlchemyError),
        ):
            upload_entry_service.process_staged_upload(7, "abc.gpx", platform.storage, db)

        platform.storage.delete.assert_not_called()

    def test_a_gz_that_decompresses_to_an_unsupported_payload_is_rejected(self):
        db = MagicMock()
        platform = _platform()
        _blob(platform, b"\x1f\x8b")
        with (
            patch.object(
                upload_entry_service.core_file_uploads, "decompress_gzip", return_value=("/tmp/x.exe", ".exe")
            ),
            patch.object(upload_entry_service.core_file_uploads, "remove_files"),
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            upload_entry_service.process_staged_upload(7, "abc.gz", platform.storage, db)

    def test_removes_the_working_directory_on_every_path(self):
        db = MagicMock()
        platform = _platform()
        _blob(platform, b"<gpx/>")
        with (
            patch.object(
                upload_entry_service.activity_ingestion_pipeline_service,
                "store_activities_from_file",
                side_effect=OSError("boom"),
            ),
            patch.object(upload_entry_service.core_file_uploads, "remove_files"),
            patch.object(upload_entry_service.shutil, "rmtree") as rmtree,
            pytest.raises(core_exceptions.ProcessingError),
        ):
            upload_entry_service.process_staged_upload(7, "abc.gpx", platform.storage, db)

        rmtree.assert_called_once()


class TestDiscardStagedUpload:
    def test_deletes_the_blob(self):
        platform = _platform()
        upload_entry_service.discard_staged_upload("abc.gpx", platform.storage)
        platform.storage.delete.assert_called_once_with(
            upload_entry_service.UPLOAD_STAGING_STORAGE_AREA,
            "upload_staging/abc.gpx",
        )

    def test_a_storage_failure_never_propagates(self):
        """Cleanup must not turn a finished import into a failed one."""
        platform = _platform()
        platform.storage.delete.side_effect = RuntimeError("bucket down")
        upload_entry_service.discard_staged_upload("abc.gpx", platform.storage)


class TestLocalStorageStaging:
    def test_staged_upload_round_trips_and_is_deleted(self, local_storage, tmp_path):
        platform = MagicMock()
        platform.storage = local_storage
        parsed_data: list[bytes] = []
        incoming = tmp_path / "x.gpx"
        incoming.write_bytes(b"<gpx/>")
        received = upload_entry_service.ReceivedUpload(incoming_path=str(incoming), storage_key="abc.gpx")

        def store_materialized_file(_user_id, file_path, *_args, **_kwargs):
            parsed_data.append(Path(file_path).read_bytes())
            return []

        with patch.object(upload_entry_service.core_file_uploads, "remove_files"):
            upload_entry_service.store_received_upload(received, platform.storage)
            assert (
                local_storage.get(upload_entry_service.UPLOAD_STAGING_STORAGE_AREA, "upload_staging/abc.gpx")
                == b"<gpx/>"
            )

            with patch.object(
                upload_entry_service.activity_ingestion_pipeline_service,
                "store_activities_from_file",
                side_effect=store_materialized_file,
            ):
                assert upload_entry_service.process_staged_upload(7, "abc.gpx", platform.storage, MagicMock()) == []

            assert parsed_data == [b"<gpx/>"]
            # Processing leaves the blob; only the caller's explicit discard removes it.
            assert (
                local_storage.get(upload_entry_service.UPLOAD_STAGING_STORAGE_AREA, "upload_staging/abc.gpx")
                == b"<gpx/>"
            )

            upload_entry_service.discard_staged_upload("abc.gpx", platform.storage)

        assert local_storage.get(upload_entry_service.UPLOAD_STAGING_STORAGE_AREA, "upload_staging/abc.gpx") is None
