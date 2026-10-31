"""Filesystem-level check that a staged upload really transits the incoming dir."""

import io
import pathlib
from functools import partial
from unittest.mock import MagicMock, patch

import pytest
from starlette.datastructures import UploadFile

import core.config as core_config
import modules.activities.activity_ingestion.upload_entry_service as upload_entry_service


def _skip_validator(coro):
    """Stand in for ``_run_validator_sync``, closing the coroutine it was handed.

    The caller builds the ``validate_upload`` coroutine before passing it in, so
    bypassing the validator without closing it leaves it unawaited.
    """
    coro.close()


def _receive(upload: UploadFile) -> upload_entry_service.ReceivedUpload:
    """Receive an upload through the real writer, bound the way the router binds it."""
    return upload_entry_service.receive_upload(
        upload.filename, partial(upload_entry_service.core_file_uploads.save_validated_upload_sync, upload)
    )


class TestStagingTransit:
    def test_the_upload_lands_in_incoming_then_moves_to_storage(self, tmp_path):
        """The incoming file exists while storage takes the bytes, and not after.

        Exercises the real writer against a real directory rather than mocking
        it, because the whole point of the two locations is that the request
        streams to disk (bounded, signature-checked) before the bytes are handed
        to the provider — a regression that skipped the incoming file would keep
        every mocked test green.
        """
        incoming = tmp_path / "upload_incoming"
        observed: dict = {}

        platform = MagicMock()

        def record_save(area, key, source):
            # Snapshot the incoming dir at the exact moment storage is handed
            # the bytes, which is the only window the file exists in.
            observed["during"] = sorted(p.name for p in incoming.iterdir())
            observed["area"] = area
            observed["bytes"] = source.read()

        platform.storage.save_stream.side_effect = record_save

        upload = UploadFile(filename="ride.gpx", file=io.BytesIO(b"<gpx></gpx>"))

        with (
            patch.object(core_config, "FILES_UPLOAD_INCOMING_DIR", str(incoming)),
            # The safeuploads validator is covered by its own tests; this one is
            # about where the bytes go.
            patch.object(upload_entry_service.core_file_uploads, "_run_validator_sync", side_effect=_skip_validator),
        ):
            key = upload_entry_service.store_received_upload(_receive(upload), platform.storage)

        # It really was written to disk first, under the server-generated name.
        assert observed["during"] == [key]
        assert observed["bytes"] == b"<gpx></gpx>"
        assert observed["area"] == upload_entry_service.UPLOAD_STAGING_STORAGE_AREA
        # …and the local copy is gone once the provider owns it, so the incoming
        # directory never accumulates.
        assert list(incoming.iterdir()) == []

    def test_the_incoming_directory_is_created_on_demand(self, tmp_path):
        """A fresh install has no directory until the first upload needs one."""
        incoming = tmp_path / "not-yet"
        platform = MagicMock()
        upload = UploadFile(filename="ride.gpx", file=io.BytesIO(b"<gpx></gpx>"))

        assert not incoming.exists()
        with (
            patch.object(core_config, "FILES_UPLOAD_INCOMING_DIR", str(incoming)),
            patch.object(upload_entry_service.core_file_uploads, "_run_validator_sync", side_effect=_skip_validator),
        ):
            upload_entry_service.store_received_upload(_receive(upload), platform.storage)

        assert incoming.is_dir()

    def test_a_storage_failure_does_not_leak_the_incoming_file(self, tmp_path):
        """Otherwise a failing bucket would slowly fill the data volume."""
        incoming = tmp_path / "upload_incoming"
        platform = MagicMock()
        platform.storage.save_stream.side_effect = RuntimeError("bucket down")
        upload = UploadFile(filename="ride.gpx", file=io.BytesIO(b"<gpx></gpx>"))

        with (
            patch.object(core_config, "FILES_UPLOAD_INCOMING_DIR", str(incoming)),
            patch.object(upload_entry_service.core_file_uploads, "_run_validator_sync", side_effect=_skip_validator),
            pytest.raises(RuntimeError),
        ):
            upload_entry_service.store_received_upload(_receive(upload), platform.storage)

        assert list(pathlib.Path(incoming).iterdir()) == []
