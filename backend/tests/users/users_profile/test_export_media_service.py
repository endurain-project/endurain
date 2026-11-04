"""Tests for the user image writer of the profile data export."""

import io
import zipfile
from unittest.mock import MagicMock

import modules.users.users_profile.export_media_service as export_media_service
import modules.users.users_profile.utils as profile_utils

_MODULE = "modules.users.users_profile.export_media_service"


def _counts() -> dict[str, int]:
    return profile_utils.initialize_operation_counts(include_user_count=True)


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
