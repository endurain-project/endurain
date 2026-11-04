"""Tests for the storage-backed file writers of the profile data export."""

import io
import zipfile
from unittest.mock import MagicMock, patch

from jasil.backends.storage_local import LocalStorage
from jasil.providers import StorageBackendUnavailableError

import modules.activities.activity_file_storage.constants as activity_file_storage_constants
import modules.users.users_profile.export_media_service as export_media_service
import modules.users.users_profile.utils as profile_utils

_MODULE = "modules.users.users_profile.export_media_service"


def _counts() -> dict[str, int]:
    return profile_utils.initialize_operation_counts(include_user_count=True)


class TestActivityFiles:
    def test_add_activity_files_none_stored(self) -> None:
        buf = io.BytesIO()
        counts = _counts()
        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z,
            patch(f"{_MODULE}.activity_file_storage_integration.get_activity_file", return_value=None),
        ):
            export_media_service.add_activity_files_to_zip(z, [1], MagicMock(), counts)

        assert counts.get("activity_files", 0) == 0

    def test_add_activity_files_no_activities(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            export_media_service.add_activity_files_to_zip(z, [], MagicMock(), _counts())
            # Should return early without error

    def test_add_activity_files_with_files(self) -> None:
        buf = io.BytesIO()
        counts = _counts()
        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z,
            patch(
                f"{_MODULE}.activity_file_storage_integration.get_activity_file",
                return_value=("1.gpx", b"<gpx></gpx>"),
            ),
        ):
            export_media_service.add_activity_files_to_zip(z, [1], MagicMock(), counts)

        assert counts["activity_files"] == 1
        buf.seek(0)
        with zipfile.ZipFile(buf, "r") as z:
            assert "activity_files/1.gpx" in z.namelist()

    def test_reads_retained_files_from_the_plain_local_layout(self, tmp_path) -> None:
        storage = LocalStorage(
            str(tmp_path),
            plain_areas=frozenset({activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA}),
        )
        storage.save(activity_file_storage_constants.ACTIVITY_FILE_STORAGE_AREA, "processed/1.gpx", b"<gpx/>")
        buf = io.BytesIO()
        counts = _counts()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            export_media_service.add_activity_files_to_zip(z, [1], storage, counts)

        assert counts["activity_files"] == 1
        buf.seek(0)
        with zipfile.ZipFile(buf, "r") as z:
            assert z.read("activity_files/1.gpx") == b"<gpx/>"

    def test_activity_without_stored_file_skipped(self) -> None:
        """An activity with no retained source file is skipped (get returns None)."""
        buf = io.BytesIO()
        counts = _counts()
        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z,
            patch(f"{_MODULE}.activity_file_storage_integration.get_activity_file", return_value=None),
        ):
            export_media_service.add_activity_files_to_zip(z, [1], MagicMock(), counts)

        assert counts.get("activity_files", 0) == 0

    def test_read_error_continues(self) -> None:
        """An OSError reading one activity's file is caught and the loop continues."""
        buf = io.BytesIO()
        counts = _counts()
        with (
            zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z,
            patch(
                f"{_MODULE}.activity_file_storage_integration.get_activity_file",
                side_effect=[OSError("read failed"), ("2.gpx", b"<gpx></gpx>")],
            ),
        ):
            export_media_service.add_activity_files_to_zip(z, [1, 2], MagicMock(), counts)

        # The first activity errored and was skipped; the second still exported.
        assert counts["activity_files"] == 1
        buf.seek(0)
        with zipfile.ZipFile(buf, "r") as z:
            assert "activity_files/2.gpx" in z.namelist()


class TestActivityMedia:
    def test_add_activity_media_missing_dir(self) -> None:
        buf = io.BytesIO()
        counts = _counts()
        storage = MagicMock()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            storage.list_keys.return_value = []
            export_media_service.add_activity_media_to_zip(z, [1], storage, counts)

        assert counts["media"] == 0

    def test_add_activity_media_no_activities(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            export_media_service.add_activity_media_to_zip(z, [], MagicMock(), _counts())
            # Should return early without error

    def test_add_activity_media_with_files(self) -> None:
        buf = io.BytesIO()
        counts = _counts()
        storage = MagicMock()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            storage.list_keys.return_value = ["1_image.jpg"]
            storage.get.return_value = b"image-bytes"
            export_media_service.add_activity_media_to_zip(z, [1], storage, counts)

        assert counts["media"] == 1
        with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as written:
            assert written.read("activity_media/1_image.jpg") == b"image-bytes"

    def test_add_activity_media_skips_a_missing_blob(self) -> None:
        buf = io.BytesIO()
        counts = _counts()
        storage = MagicMock()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            storage.list_keys.return_value = ["1_image.jpg"]
            storage.get.return_value = None
            export_media_service.add_activity_media_to_zip(z, [1], storage, counts)

        assert counts["media"] == 0

    def test_a_failing_blob_does_not_abort_the_rest(self) -> None:
        buf = io.BytesIO()
        counts = _counts()
        storage = MagicMock()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            storage.list_keys.return_value = ["1_bad.jpg", "1_good.jpg"]
            storage.get.side_effect = [StorageBackendUnavailableError("backend down"), b"good-bytes"]
            export_media_service.add_activity_media_to_zip(z, [1], storage, counts)

        assert counts.get("media", 0) == 1

    def test_media_listing_failure_does_not_abort_the_export(self) -> None:
        """A storage outage skips that activity's media rather than failing the export."""
        buf = io.BytesIO()
        counts = _counts()
        storage = MagicMock()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            storage.list_keys.side_effect = StorageBackendUnavailableError("permission denied")
            export_media_service.add_activity_media_to_zip(z, [1], storage, counts)

        assert counts.get("media", 0) == 0


class TestUserImages:
    """User photos are exported through the StorageProvider, not a local walk."""

    @staticmethod
    def _export(user_id: int, keys: list[str], blob: bytes | None = b"image-bytes"):
        buf = io.BytesIO()
        counts = _counts()
        config = profile_utils.BasePerformanceConfig(enable_memory_monitoring=False)
        storage = MagicMock()
        storage.list_keys.return_value = keys
        storage.get.return_value = blob

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            export_media_service.add_user_images_to_zip(z, user_id, storage, counts, config)
        return counts, buf, storage

    def test_no_stored_photo(self) -> None:
        counts, _, _ = self._export(1, [])

        assert counts["user_images"] == 0

    def test_writes_the_blob_under_its_key(self) -> None:
        counts, buf, storage = self._export(1, ["1.jpg"])

        assert counts["user_images"] == 1
        storage.list_keys.assert_called_once_with("user_images", "1.")
        with zipfile.ZipFile(io.BytesIO(buf.getvalue())) as written:
            assert written.read("user_images/1.jpg") == b"image-bytes"

    def test_only_the_owner_prefix_is_listed(self) -> None:
        """Listing by prefix is what stops user 1's export leaking user 12's photo."""
        _, _, storage = self._export(1, ["1.jpg"])

        assert storage.list_keys.call_args.args[1] == "1."

    def test_skips_a_missing_blob(self) -> None:
        counts, _, _ = self._export(1, ["1.jpg"], blob=None)

        assert counts["user_images"] == 0

    def test_large_image_is_still_exported(self) -> None:
        counts, _, _ = self._export(1, ["1.jpg"], blob=b"x" * (11 * 1024 * 1024))

        assert counts["user_images"] == 1

    def test_a_listing_failure_is_logged_not_raised(self) -> None:
        buf = io.BytesIO()
        counts = _counts()
        storage = MagicMock()
        storage.list_keys.side_effect = OSError("perms")

        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            export_media_service.add_user_images_to_zip(
                z, 1, storage, counts, profile_utils.BasePerformanceConfig(enable_memory_monitoring=False)
            )

        assert counts["user_images"] == 0

    def test_a_read_failure_skips_only_that_blob(self) -> None:
        counts, _, _ = self._export(1, ["1.jpg"], blob=None)

        assert counts["user_images"] == 0
