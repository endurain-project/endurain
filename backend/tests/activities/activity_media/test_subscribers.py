"""Tests for the ``activity.deleted`` media cleanup subscriber.

Deleting an activity cascades its ``activity_media`` rows but used to leave the
image blobs behind forever — a storage leak and a privacy problem, since an
athlete deleting an activity expects its photos to go too.
"""

import uuid
from unittest.mock import MagicMock, patch

import jasil.providers as platform_providers
import pytest
from jasil.backends.storage_local import LocalStorage

import modules.activities.activity_media.service as media_service
import modules.activities.activity_media.subscribers as media_subscribers

ACT = uuid.UUID("00000000-0000-4000-8000-000000000042")
OTHER = uuid.UUID("00000000-0000-4000-8000-000000000043")

_SVC = "modules.activities.activity_media.service"
_AREA = "activity_media"


def _local_storage(tmp_path):
    """Return a real ``LocalStorage`` rooted at ``tmp_path``.

    The real backend rather than a mock, because half of what is being asserted
    here (prefix matching, symlink containment, skipping directories) lives in
    ``list_keys`` itself.
    """
    return LocalStorage(str(tmp_path), legacy_layout=True)


def _area_dir(tmp_path):
    """Create and return the media area directory under ``tmp_path``."""
    area = tmp_path / _AREA
    area.mkdir(parents=True, exist_ok=True)
    return area


class TestDeleteMediaFilesForActivity:
    def test_removes_only_the_activitys_blobs(self, tmp_path):
        area = _area_dir(tmp_path)
        (area / f"{ACT}_aaa.jpeg").write_bytes(b"x")
        (area / f"{ACT}_bbb.png").write_bytes(b"x")
        (area / f"{OTHER}_ccc.jpeg").write_bytes(b"x")

        storage = _local_storage(tmp_path)
        removed = media_service.delete_media_files_for_activity(ACT, storage)

        assert removed == 2
        assert not (area / f"{ACT}_aaa.jpeg").exists()
        assert not (area / f"{ACT}_bbb.png").exists()
        assert (area / f"{OTHER}_ccc.jpeg").exists()

    def test_another_activitys_and_an_integer_layout_blob_are_not_a_match(self, tmp_path):
        area = _area_dir(tmp_path)
        (area / f"{OTHER}_aaa.jpeg").write_bytes(b"x")
        (area / "42_bbb.jpeg").write_bytes(b"x")

        storage = _local_storage(tmp_path)
        removed = media_service.delete_media_files_for_activity(ACT, storage)

        assert removed == 0
        assert (area / f"{OTHER}_aaa.jpeg").exists()
        assert (area / "42_bbb.jpeg").exists()

    def test_activity_without_media_is_a_no_op(self, tmp_path):
        _area_dir(tmp_path)
        storage = _local_storage(tmp_path)
        assert media_service.delete_media_files_for_activity(ACT, storage) == 0

    def test_is_idempotent(self, tmp_path):
        area = _area_dir(tmp_path)
        (area / f"{ACT}_aaa.jpeg").write_bytes(b"x")

        storage = _local_storage(tmp_path)
        assert media_service.delete_media_files_for_activity(ACT, storage) == 1
        assert media_service.delete_media_files_for_activity(ACT, storage) == 0

    def test_missing_area_directory_is_a_no_op(self, tmp_path):
        storage = _local_storage(tmp_path / "does-not-exist")
        assert media_service.delete_media_files_for_activity(ACT, storage) == 0

    def test_directories_are_left_alone(self, tmp_path):
        area = _area_dir(tmp_path)
        (area / f"{ACT}_subdir").mkdir()

        storage = _local_storage(tmp_path)
        assert media_service.delete_media_files_for_activity(ACT, storage) == 0

        assert (area / f"{ACT}_subdir").is_dir()

    def test_a_symlink_out_of_the_area_is_not_followed(self, tmp_path):
        # Defence in depth: a symlink must not let cleanup delete outside the
        # storage area.
        outside = tmp_path / "outside.jpeg"
        outside.write_bytes(b"x")
        area = _area_dir(tmp_path)
        (area / f"{ACT}_link.jpeg").symlink_to(outside)

        storage = _local_storage(tmp_path)
        removed = media_service.delete_media_files_for_activity(ACT, storage)

        assert removed == 0
        assert outside.exists()

    def test_a_storage_failure_propagates_so_the_runner_retries(self):
        storage = MagicMock()
        storage.list_keys.return_value = [f"{ACT}_aaa.jpeg", f"{ACT}_bbb.jpeg"]
        storage.delete.side_effect = platform_providers.StorageBackendUnavailableError("storage down")

        with pytest.raises(platform_providers.StorageBackendUnavailableError):
            media_service.delete_media_files_for_activity(ACT, storage)


class TestListMediaBlobs:
    def test_a_listing_failure_propagates(self):
        storage = MagicMock()
        storage.list_keys.side_effect = platform_providers.StorageBackendUnavailableError("storage down")

        with pytest.raises(platform_providers.StorageBackendUnavailableError):
            media_service.list_media_blobs(ACT, storage)

    def test_an_unreadable_blob_is_skipped(self):
        storage = MagicMock()
        storage.list_keys.return_value = [f"{ACT}_aaa.jpeg", f"{ACT}_bbb.jpeg"]
        storage.get.side_effect = [platform_providers.StorageBackendUnavailableError("storage down"), b"x"]

        assert media_service.list_media_blobs(ACT, storage) == [(f"{ACT}_bbb.jpeg", b"x")]


class TestCleanupSubscriber:
    @staticmethod
    def _event(payload: dict):
        """Build a real envelope — the handler reads ``schema_version`` off it."""
        from jasil.events import new_event

        return new_event("activity.deleted", payload, source="test")

    def test_durable_handler_cleans_up_by_activity_id(self):
        event = self._event({"activity_id": str(ACT)})

        with (
            patch.object(media_subscribers.platform_runtime, "get_active_platform") as platform,
            patch.object(media_subscribers.activity_media_service, "delete_media_files_for_activity") as cleanup,
        ):
            media_subscribers.cleanup_activity_media_for_event(event)

        cleanup.assert_called_once_with(ACT, platform.return_value.storage)

    def test_durable_handler_rejects_a_malformed_payload(self):
        # Raising is what lets the durable runner retry / dead-letter instead of
        # marking a malformed job complete.
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            media_subscribers.cleanup_activity_media_for_event(self._event({}))

    def test_bus_subscriber_swallows_failures(self):
        # A cleanup failure must never break activity deletion.
        with patch.object(
            media_subscribers.activity_media_service,
            "delete_media_files_for_activity",
            side_effect=OSError("disk gone"),
        ):
            media_subscribers.on_activity_deleted_cleanup_media(MagicMock(payload={"activity_id": str(ACT)}))
