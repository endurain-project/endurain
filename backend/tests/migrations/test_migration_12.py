"""Tests for migration 12: stored images lose their metadata."""

import io
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from jasil.backends.storage_local import LocalStorage
from PIL import Image
from sqlalchemy.orm import Session
from tests._helpers import images

import migrations.migration_12 as migration_12
import migrations.utils as migrations_utils
import modules.activities.activity_media.contracts as activity_media_contracts

_MODULE = "migrations.migration_12"
_USER = uuid.UUID("11111111-1111-4111-8111-111111111111")
_OTHER_USER = uuid.UUID("22222222-2222-4222-8222-222222222222")
_JPEG = images.jpeg_with_exif((2000, 1000))
_PNG = images.png_with_text()


def _media(media_id: uuid.UUID, key: str) -> activity_media_contracts.ActivityMediaRecord:
    return activity_media_contracts.ActivityMediaRecord(
        id=media_id, activity_id=uuid.uuid4(), media_path=key, media_type=1, content_hash=None
    )


def _run(storage: LocalStorage, *, photo_keys: list[tuple[uuid.UUID, str | None]], media: list[str]):
    db = MagicMock(spec=Session)
    with (
        patch(f"{_MODULE}.platform_runtime") as runtime,
        patch(f"{_MODULE}.migrations_service") as migrations_service,
        patch(f"{_MODULE}.users_migration_service.get_stored_photo_keys", return_value=photo_keys),
        patch(
            f"{_MODULE}.activity_media_migration_service.get_all_activity_media",
            return_value=[_media(uuid.uuid4(), key) for key in media],
        ),
    ):
        runtime.get_active_platform.return_value.storage = storage
        migration_12.process_migration_12(db)
    return db, migrations_service


class TestProcessMigration12:
    def test_is_registered_as_a_synchronous_data_migration(self):
        assert migrations_utils._SYNC_MIGRATIONS[12] is migration_12.process_migration_12

    def test_strips_avatars_and_caps_them_at_512_pixels(self, tmp_path: Path):
        storage = LocalStorage(str(tmp_path))
        storage.save("user_images", "7.jpg", _JPEG, "image/jpeg")

        db, migrations_service = _run(storage, photo_keys=[(_USER, "7.jpg"), (_OTHER_USER, None)], media=[])

        stored = storage.get("user_images", "7.jpg")
        assert stored is not None
        assert not images.has_metadata(stored)
        with Image.open(io.BytesIO(stored)) as image:
            assert image.format == "JPEG"
            assert image.size == (512, 256)
        migrations_service.mark_executed.assert_called_once_with(12, db)

    def test_strips_activity_photos_without_resizing_them(self, tmp_path: Path):
        storage = LocalStorage(str(tmp_path))
        storage.save("activity_media", "1_a.jpg", _JPEG, "image/jpeg")
        storage.save("activity_media", "1_b.png", _PNG, "image/png")

        _run(storage, photo_keys=[], media=["1_a.jpg", "1_b.png"])

        jpeg = storage.get("activity_media", "1_a.jpg")
        png = storage.get("activity_media", "1_b.png")
        assert jpeg is not None and png is not None
        assert not images.has_metadata(jpeg)
        assert not images.has_metadata(png)
        with Image.open(io.BytesIO(jpeg)) as image:
            assert image.size == (2000, 1000)

    def test_strips_the_login_photo_and_identity_provider_icons(self, tmp_path: Path):
        storage = LocalStorage(str(tmp_path))
        storage.save("server_images", "login.png", _PNG, "image/png")
        storage.save("identity_provider_icons", "3", _PNG, "image/png")

        _run(storage, photo_keys=[], media=[])

        for area, key in (("server_images", "login.png"), ("identity_provider_icons", "3")):
            stored = storage.get(area, key)
            assert stored is not None
            assert not images.has_metadata(stored)

    def test_one_unreadable_image_is_skipped_and_the_rest_are_rewritten(self, tmp_path: Path):
        storage = LocalStorage(str(tmp_path))
        storage.save("activity_media", "1_bad.jpg", b"not an image", "image/jpeg")
        storage.save("activity_media", "1_good.jpg", _JPEG, "image/jpeg")

        _, migrations_service = _run(storage, photo_keys=[], media=["1_bad.jpg", "1_good.jpg"])

        assert storage.get("activity_media", "1_bad.jpg") == b"not an image"
        good = storage.get("activity_media", "1_good.jpg")
        assert good is not None and not images.has_metadata(good)
        migrations_service.mark_executed.assert_called_once()

    def test_a_key_with_no_stored_object_is_skipped(self, tmp_path: Path):
        storage = LocalStorage(str(tmp_path))

        _, migrations_service = _run(storage, photo_keys=[(_USER, "7.jpg")], media=["1_missing.jpg"])

        migrations_service.mark_executed.assert_called_once()

    def test_no_database_transaction_stays_open_across_storage_calls(self, tmp_path: Path):
        storage = LocalStorage(str(tmp_path))
        storage.save("activity_media", "1_a.jpg", _JPEG, "image/jpeg")
        steps: list[str] = []
        db = MagicMock(spec=Session)
        db.rollback.side_effect = lambda: steps.append("rollback")
        original_get = storage.get

        def get(area: str, key: str):
            steps.append("get")
            return original_get(area, key)

        with (
            patch(f"{_MODULE}.platform_runtime") as runtime,
            patch(f"{_MODULE}.migrations_service"),
            patch(f"{_MODULE}.users_migration_service.get_stored_photo_keys", return_value=[]),
            patch(
                f"{_MODULE}.activity_media_migration_service.get_all_activity_media",
                return_value=[_media(uuid.uuid4(), "1_a.jpg")],
            ),
            patch.object(storage, "get", side_effect=get),
        ):
            runtime.get_active_platform.return_value.storage = storage
            migration_12.process_migration_12(db)

        assert steps[0] == "rollback"
        assert "get" in steps

    def test_a_failed_listing_leaves_the_migration_pending(self):
        db = MagicMock(spec=Session)
        with (
            patch(f"{_MODULE}.platform_runtime") as runtime,
            patch(f"{_MODULE}.migrations_service") as migrations_service,
            patch(f"{_MODULE}.users_migration_service.get_stored_photo_keys", side_effect=RuntimeError("db down")),
        ):
            runtime.get_active_platform.return_value.storage = MagicMock()
            migration_12.process_migration_12(db)

        migrations_service.mark_executed.assert_not_called()
