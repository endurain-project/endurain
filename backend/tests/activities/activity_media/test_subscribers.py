"""Tests for the ``activity.deleted`` media cleanup subscriber.

Deleting an activity cascades its ``activity_media`` rows but used to leave the
image files on disk forever — a storage leak and a privacy problem, since an
athlete deleting an activity expects its photos to go too.
"""

from unittest.mock import MagicMock, patch

import pytest

import modules.activities.activity_media.service as media_service
import modules.activities.activity_media.subscribers as media_subscribers

_SVC = "modules.activities.activity_media.service"


def _media_dir(tmp_path):
    """Point the service's media directory at ``tmp_path``."""
    return patch.object(media_service.core_config.settings, "ACTIVITY_MEDIA_DIR", str(tmp_path))


class TestDeleteMediaFilesForActivity:
    def test_removes_only_the_activitys_files(self, tmp_path):
        (tmp_path / "42_aaa.jpeg").write_bytes(b"x")
        (tmp_path / "42_bbb.png").write_bytes(b"x")
        (tmp_path / "43_ccc.jpeg").write_bytes(b"x")

        with _media_dir(tmp_path):
            removed = media_service.delete_media_files_for_activity(42)

        assert removed == 2
        assert not (tmp_path / "42_aaa.jpeg").exists()
        assert not (tmp_path / "42_bbb.png").exists()
        assert (tmp_path / "43_ccc.jpeg").exists()

    def test_an_id_prefix_is_not_a_match(self, tmp_path):
        # Activity 42 must not delete activity 421's media.
        (tmp_path / "421_aaa.jpeg").write_bytes(b"x")
        (tmp_path / "4_bbb.jpeg").write_bytes(b"x")

        with _media_dir(tmp_path):
            removed = media_service.delete_media_files_for_activity(42)

        assert removed == 0
        assert (tmp_path / "421_aaa.jpeg").exists()
        assert (tmp_path / "4_bbb.jpeg").exists()

    def test_activity_without_media_is_a_no_op(self, tmp_path):
        with _media_dir(tmp_path):
            assert media_service.delete_media_files_for_activity(42) == 0

    def test_is_idempotent(self, tmp_path):
        (tmp_path / "42_aaa.jpeg").write_bytes(b"x")

        with _media_dir(tmp_path):
            assert media_service.delete_media_files_for_activity(42) == 1
            assert media_service.delete_media_files_for_activity(42) == 0

    def test_missing_media_directory_is_a_no_op(self, tmp_path):
        with _media_dir(tmp_path / "does-not-exist"):
            assert media_service.delete_media_files_for_activity(42) == 0

    def test_directories_are_left_alone(self, tmp_path):
        (tmp_path / "42_subdir").mkdir()

        with _media_dir(tmp_path):
            assert media_service.delete_media_files_for_activity(42) == 0

        assert (tmp_path / "42_subdir").is_dir()

    def test_a_symlink_out_of_the_media_dir_is_not_followed(self, tmp_path):
        # Defence in depth: a symlink must not let cleanup delete outside the
        # media directory.
        outside = tmp_path / "outside.jpeg"
        outside.write_bytes(b"x")
        media_dir = tmp_path / "media"
        media_dir.mkdir()
        (media_dir / "42_link.jpeg").symlink_to(outside)

        with _media_dir(media_dir):
            removed = media_service.delete_media_files_for_activity(42)

        assert removed == 0
        assert outside.exists()

    def test_an_unremovable_file_does_not_abort_the_rest(self, tmp_path):
        (tmp_path / "42_aaa.jpeg").write_bytes(b"x")
        (tmp_path / "42_bbb.jpeg").write_bytes(b"x")
        real_unlink = media_service.Path.unlink

        def _flaky_unlink(self, *args, **kwargs):
            if self.name == "42_aaa.jpeg":
                raise OSError("permission denied")
            return real_unlink(self, *args, **kwargs)

        with _media_dir(tmp_path), patch.object(media_service.Path, "unlink", _flaky_unlink):
            removed = media_service.delete_media_files_for_activity(42)

        assert removed == 1


class TestCleanupSubscriber:
    @staticmethod
    def _event(payload: dict):
        """Build a real envelope — the handler reads ``schema_version`` off it."""
        from infra.events import new_event

        return new_event("activity.deleted", payload, source="test")

    def test_durable_handler_cleans_up_by_activity_id(self):
        event = self._event({"activity_id": 42})

        with patch.object(media_subscribers.activity_media_service, "delete_media_files_for_activity") as cleanup:
            media_subscribers.cleanup_activity_media_for_event(event)

        cleanup.assert_called_once_with(42)

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
            media_subscribers.on_activity_deleted_cleanup_media(MagicMock(payload={"activity_id": 42}))
