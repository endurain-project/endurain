"""Tests for migration 13: stored files named by an integer id are renamed to their UUID."""

import io
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from botocore.exceptions import ClientError
from jasil.backends.storage_local import LocalStorage
from jasil.backends.storage_s3 import S3Storage
from sqlalchemy.orm import Session

import core.config as core_config
import migrations.migration_13 as migration_13
import migrations.models as migrations_models
import migrations.utils as migrations_utils
import modules.activities.activity.models as activity_models
import modules.activities.activity_media.models as activity_media_models
import modules.users.users.models as users_models
from core.database import Base

_MODULE = "migrations.migration_13"
_AREA = "identity_provider_icons"
_FIRST = uuid.UUID("11111111-1111-4111-8111-111111111111")
_SECOND = uuid.UUID("22222222-2222-4222-8222-222222222222")
_FILES = "activity_files"
_THUMBNAILS = "activity_thumbnails"
_MEDIA = "activity_media"
_ACTIVITY = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
_OTHER_ACTIVITY = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
_MEDIA_ROW = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
_OTHER_MEDIA_ROW = uuid.UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
_USER = uuid.UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
_OTHER_USER = uuid.UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
_PHOTOS = "user_images"
_IMPORT_ERRORS = "bulk_import_errors"
_EXPORTS = "profile_export_staging"
_IMPORTS = "profile_import_staging"
_USER_COLUMNS = {
    "name": "Name",
    "username": "name",
    "email": "name@example.org",
    "password": "x",
    "birthdate": datetime(2000, 1, 1).date(),
    "gender": 1,
    "units": 1,
    "height": 170,
    "preferred_language": "us",
    "first_day_of_week": 0,
    "currency": 1,
    "access_type": "regular",
    "active": True,
    "email_verified": True,
    "created_at": datetime(2026, 1, 1),
}
_ACTIVITY_COLUMNS = {
    "distance": 1,
    "activity_type": 1,
    "start_time": datetime(2026, 1, 1),
    "end_time": datetime(2026, 1, 1),
    "total_elapsed_time": 1,
    "total_timer_time": 1,
    "created_at": datetime(2026, 1, 1),
    "user_id": _USER,
    **{column.name: False for column in activity_models.Activity.__table__.c if column.name.startswith("hide_")},
}
_IDS = sa.Table(
    "uuid_migration_ids",
    sa.MetaData(),
    sa.Column("table_name", sa.String(64), primary_key=True),
    sa.Column("old_id", sa.Integer, primary_key=True),
    sa.Column("new_id", sa.Uuid, nullable=False),
)

_RECORDED_IDS = [
    {"table_name": "identity_providers", "old_id": 1, "new_id": _FIRST},
    {"table_name": "identity_providers", "old_id": 2, "new_id": _SECOND},
    {"table_name": "activities", "old_id": 1, "new_id": _ACTIVITY},
    {"table_name": "activities", "old_id": 3, "new_id": _OTHER_ACTIVITY},
    {"table_name": "users", "old_id": 1, "new_id": _USER},
    {"table_name": "users", "old_id": 2, "new_id": _OTHER_USER},
]


class _FailingCopy(LocalStorage):
    """A storage that cannot copy the object stored under the key ``fail``."""

    fail = ""

    def copy(self, src_area: str, src_key: str, dst_area: str, dst_key: str) -> None:
        if src_key == self.fail:
            raise OSError("disk full")
        super().copy(src_area, src_key, dst_area, dst_key)


class _FailingListing(LocalStorage):
    """A storage whose listing fails while ``failing`` is set."""

    failing = True

    def list_keys(self, area: str, prefix: str) -> list[str]:
        if self.failing:
            raise OSError("storage unavailable")
        return super().list_keys(area, prefix)


class _FakeS3Client:
    """The slice of a boto3 S3 client that ``S3Storage`` calls for listing, existence, copy and delete, in memory.

    The calls take boto3's capitalised keyword names (``Key``, ``Prefix``), which is why they arrive as ``call``.
    """

    fail_copy_to: str | None = None

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, **call: Any) -> None:
        self.objects[call["Key"]] = call["Body"]

    def get_object(self, **call: Any) -> dict[str, io.BytesIO]:
        return {"Body": io.BytesIO(self.objects[call["Key"]])}

    def head_object(self, **call: Any) -> dict[str, object]:
        if call["Key"] not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"ContentLength": len(self.objects[call["Key"]]), "LastModified": datetime(2026, 1, 1)}

    def delete_object(self, **call: Any) -> None:
        self.objects.pop(call["Key"], None)

    def copy(self, copy_source: dict[str, str], bucket: str, key: str) -> None:
        if self.fail_copy_to is not None and key.endswith(self.fail_copy_to):
            raise ClientError({"Error": {"Code": "500"}}, "CopyObject")
        self.objects[key] = self.objects[copy_source["Key"]]

    def get_paginator(self, _operation: str) -> "_FakeS3Client":
        return self

    def paginate(self, **call: Any) -> list[dict[str, list[dict[str, object]]]]:
        return [
            {
                "Contents": [
                    {"Key": key, "LastModified": datetime(2026, 1, 1)}
                    for key in sorted(self.objects)
                    if key.startswith(call["Prefix"])
                ]
            }
        ]


@pytest.fixture
def db():
    engine = sa.create_engine("sqlite://", poolclass=sa.StaticPool)
    migrations_models.Migration.__table__.create(engine)
    _IDS.create(engine)
    Base.metadata.create_all(
        engine,
        tables=[
            activity_models.Activity.__table__,
            activity_media_models.ActivityMedia.__table__,
            users_models.Users.__table__,
        ],
    )
    with Session(engine) as session:
        session.add(migrations_models.Migration(id=13, name="v0.21.0", description="rename", executed=False))
        session.execute(
            sa.insert(_IDS),
            _RECORDED_IDS,
        )
        session.execute(
            sa.insert(activity_models.Activity.__table__),
            [
                {"id": _ACTIVITY, "map_thumbnail_path": "1.webp", **_ACTIVITY_COLUMNS},
                {"id": _OTHER_ACTIVITY, "map_thumbnail_path": None, **_ACTIVITY_COLUMNS},
            ],
        )
        session.execute(
            sa.insert(activity_media_models.ActivityMedia.__table__),
            [
                {"id": _MEDIA_ROW, "activity_id": _ACTIVITY, "media_path": "1_aaa.jpg", "media_type": 1},
                {"id": _OTHER_MEDIA_ROW, "activity_id": _ACTIVITY, "media_path": "1_bbb.jpg", "media_type": 1},
            ],
        )
        session.execute(
            sa.insert(users_models.Users.__table__),
            [
                {
                    "id": _USER,
                    **_USER_COLUMNS,
                    "username": "first",
                    "email": "first@example.org",
                    "photo_path": "1.jpg",
                },
                {
                    "id": _OTHER_USER,
                    **_USER_COLUMNS,
                    "username": "second",
                    "email": "second@example.org",
                    "photo_path": "https://example.org/2.jpg",
                },
            ],
        )
        session.commit()
        yield session


def _run(storage: LocalStorage | S3Storage, db: Session) -> None:
    with patch(f"{_MODULE}.platform_runtime") as runtime:
        runtime.get_active_platform.return_value.storage = storage
        migration_13.process_migration_13(db)


def _record_the_ids_again(db: Session) -> None:
    """Put the dropped ``uuid_migration_ids`` table back as the conversion left it and mark the migration pending."""
    db.rollback()
    _IDS.create(db.connection())
    db.execute(sa.insert(_IDS), _RECORDED_IDS)
    db.execute(
        sa.update(migrations_models.Migration).where(migrations_models.Migration.id == 13).values(executed=False)
    )
    db.commit()


def _executed(db: Session) -> bool:
    return db.execute(
        sa.select(migrations_models.Migration.executed).where(migrations_models.Migration.id == 13)
    ).scalar_one()


def _table_exists(db: Session) -> bool:
    return sa.inspect(db.connection()).has_table("uuid_migration_ids")


class TestProcessMigration13:
    def test_is_registered_as_a_synchronous_data_migration(self):
        assert migrations_utils._SYNC_MIGRATIONS[13] is migration_13.process_migration_13

    def test_renames_the_icons_deletes_the_orphans_and_skips_uuid_keys(self, tmp_path: Path, db: Session):
        storage = LocalStorage(str(tmp_path))
        storage.save(_AREA, "1", b"first", "image/png")
        storage.save(_AREA, "2", b"second", "image/png")
        storage.save(_AREA, "99", b"orphan", "image/png")
        uuid_key = str(uuid.UUID("33333333-3333-4333-8333-333333333333"))
        storage.save(_AREA, uuid_key, b"kept", "image/png")

        _run(storage, db)

        assert sorted(storage.list_keys(_AREA, "")) == sorted([str(_FIRST), str(_SECOND), uuid_key])
        assert storage.get(_AREA, str(_FIRST)) == b"first"
        assert storage.get(_AREA, str(_SECOND)) == b"second"
        assert storage.get(_AREA, uuid_key) == b"kept"
        assert _executed(db) is True
        assert _table_exists(db) is False

    def test_an_existing_uuid_key_is_not_overwritten(self, tmp_path: Path, db: Session):
        storage = LocalStorage(str(tmp_path))
        storage.save(_AREA, "1", b"old", "image/png")
        storage.save(_AREA, str(_FIRST), b"already copied", "image/png")

        _run(storage, db)

        assert storage.list_keys(_AREA, "") == [str(_FIRST)]
        assert storage.get(_AREA, str(_FIRST)) == b"already copied"

    def test_a_second_run_changes_nothing(self, tmp_path: Path, db: Session):
        storage = LocalStorage(str(tmp_path))
        storage.save(_AREA, "1", b"first", "image/png")
        _run(storage, db)

        _record_the_ids_again(db)

        _run(storage, db)

        assert storage.list_keys(_AREA, "") == [str(_FIRST)]
        assert storage.get(_AREA, str(_FIRST)) == b"first"
        assert _executed(db) is True

    def test_a_failure_keeps_the_table_and_the_migration_pending_and_the_next_run_finishes(
        self, tmp_path: Path, db: Session, caplog: pytest.LogCaptureFixture
    ):
        storage = _FailingCopy(str(tmp_path))
        storage.fail = "1"
        storage.save(_AREA, "1", b"first", "image/png")
        storage.save(_AREA, "2", b"second", "image/png")

        _run(storage, db)

        assert sorted(storage.list_keys(_AREA, "")) == sorted(["1", str(_SECOND)])
        assert _executed(db) is False
        assert _table_exists(db) is True
        assert any(
            record.levelname == "ERROR" and "identity_provider_icons/1" in record.getMessage()
            for record in caplog.records
        )
        assert "first" not in caplog.text

        storage.fail = ""
        _run(storage, db)

        assert sorted(storage.list_keys(_AREA, "")) == sorted([str(_FIRST), str(_SECOND)])
        assert _executed(db) is True
        assert _table_exists(db) is False

    def test_a_failing_listing_keeps_the_table_and_the_migration_pending_and_the_next_run_finishes(
        self, tmp_path: Path, db: Session, caplog: pytest.LogCaptureFixture
    ):
        storage = _FailingListing(str(tmp_path))
        storage.save(_AREA, "1", b"first", "image/png")

        _run(storage, db)

        assert _executed(db) is False
        assert _table_exists(db) is True
        assert any(
            record.levelname == "ERROR" and "could not rename the keys" in record.getMessage()
            for record in caplog.records
        )

        storage.failing = False
        _run(storage, db)

        assert storage.list_keys(_AREA, "") == [str(_FIRST)]
        assert _executed(db) is True
        assert _table_exists(db) is False

    def test_a_missing_table_is_an_error_and_leaves_the_migration_pending(
        self, tmp_path: Path, db: Session, caplog: pytest.LogCaptureFixture
    ):
        db.execute(sa.text("DROP TABLE uuid_migration_ids"))
        db.commit()

        _run(LocalStorage(str(tmp_path)), db)

        assert _executed(db) is False
        assert any(record.levelname == "ERROR" for record in caplog.records)


def _stored_paths(db: Session) -> tuple[list[str | None], list[str | None]]:
    db.rollback()
    thumbnails = db.execute(
        sa.select(activity_models.Activity.map_thumbnail_path).order_by(activity_models.Activity.id)
    )
    media = db.execute(
        sa.select(activity_media_models.ActivityMedia.media_path).order_by(activity_media_models.ActivityMedia.id)
    )
    return sorted(thumbnails.scalars().all(), key=str), sorted(media.scalars().all())


def _save_activity_blobs(storage: LocalStorage | S3Storage) -> None:
    storage.save(_FILES, "processed/1.fit", b"fit", "application/octet-stream")
    storage.save(_FILES, "processed/999.tcx", b"orphan", "application/octet-stream")
    storage.save(_FILES, "upload_staging/abc.fit", b"staged", "application/octet-stream")
    storage.save(_THUMBNAILS, "1.webp", b"thumb", "image/webp")
    storage.save(_THUMBNAILS, "999.webp", b"orphan", "image/webp")
    storage.save(_MEDIA, "1_aaa.jpg", b"aaa", "image/jpeg")
    storage.save(_MEDIA, "1_bbb.jpg", b"bbb", "image/jpeg")
    storage.save(_MEDIA, "999_eee.jpg", b"orphan", "image/jpeg")


class TestActivityBlobs:
    def test_renames_the_files_thumbnails_and_media_and_rewrites_their_columns(self, tmp_path: Path, db: Session):
        storage = LocalStorage(str(tmp_path))
        _save_activity_blobs(storage)

        _run(storage, db)

        assert storage.list_keys(_FILES, "") == sorted([f"processed/{_ACTIVITY}.fit", "upload_staging/abc.fit"])
        assert storage.get(_FILES, f"processed/{_ACTIVITY}.fit") == b"fit"
        assert storage.list_keys(_THUMBNAILS, "") == [f"{_ACTIVITY}.webp"]
        assert storage.get(_THUMBNAILS, f"{_ACTIVITY}.webp") == b"thumb"
        assert storage.list_keys(_MEDIA, "") == [f"{_ACTIVITY}_aaa.jpg", f"{_ACTIVITY}_bbb.jpg"]
        assert storage.get(_MEDIA, f"{_ACTIVITY}_bbb.jpg") == b"bbb"
        assert _stored_paths(db) == ([None, f"{_ACTIVITY}.webp"], [f"{_ACTIVITY}_aaa.jpg", f"{_ACTIVITY}_bbb.jpg"])
        assert _executed(db) is True

    def test_a_failing_media_copy_leaves_the_columns_and_the_integer_blobs_and_the_next_run_finishes(
        self, tmp_path: Path, db: Session
    ):
        storage = _FailingCopy(str(tmp_path))
        storage.fail = "1_bbb.jpg"
        _save_activity_blobs(storage)

        _run(storage, db)

        assert _executed(db) is False
        assert _table_exists(db) is True
        assert _stored_paths(db)[1] == ["1_aaa.jpg", "1_bbb.jpg"]
        assert storage.list_keys(_MEDIA, "") == sorted(
            ["1_aaa.jpg", "1_bbb.jpg", "999_eee.jpg", f"{_ACTIVITY}_aaa.jpg"]
        )

        storage.fail = ""
        _run(storage, db)

        assert storage.list_keys(_MEDIA, "") == [f"{_ACTIVITY}_aaa.jpg", f"{_ACTIVITY}_bbb.jpg"]
        assert _stored_paths(db)[1] == [f"{_ACTIVITY}_aaa.jpg", f"{_ACTIVITY}_bbb.jpg"]
        assert _executed(db) is True

    def test_an_existing_uuid_key_is_not_overwritten(self, tmp_path: Path, db: Session):
        storage = LocalStorage(str(tmp_path))
        storage.save(_MEDIA, "1_aaa.jpg", b"old", "image/jpeg")
        storage.save(_MEDIA, f"{_ACTIVITY}_aaa.jpg", b"already copied", "image/jpeg")
        storage.save(_FILES, "processed/1.fit", b"old", "application/octet-stream")
        storage.save(_FILES, f"processed/{_ACTIVITY}.fit", b"already copied", "application/octet-stream")

        _run(storage, db)

        assert storage.get(_MEDIA, f"{_ACTIVITY}_aaa.jpg") == b"already copied"
        assert storage.get(_FILES, f"processed/{_ACTIVITY}.fit") == b"already copied"
        assert storage.list_keys(_MEDIA, "") == [f"{_ACTIVITY}_aaa.jpg"]

    def test_a_second_run_changes_nothing(self, tmp_path: Path, db: Session):
        storage = LocalStorage(str(tmp_path))
        _save_activity_blobs(storage)
        _run(storage, db)
        paths = _stored_paths(db)

        _record_the_ids_again(db)

        _run(storage, db)

        assert _stored_paths(db) == paths
        assert storage.list_keys(_MEDIA, "") == [f"{_ACTIVITY}_aaa.jpg", f"{_ACTIVITY}_bbb.jpg"]


class TestActivityBlobsOnS3:
    @pytest.fixture
    def client(self) -> _FakeS3Client:
        return _FakeS3Client()

    @pytest.fixture
    def storage(self, client: _FakeS3Client) -> S3Storage:
        return S3Storage(client, "bucket", "endurain")

    def test_renames_the_files_thumbnails_and_media_and_rewrites_their_columns(self, storage: S3Storage, db: Session):
        _save_activity_blobs(storage)

        _run(storage, db)

        assert storage.list_keys(_FILES, "") == sorted([f"processed/{_ACTIVITY}.fit", "upload_staging/abc.fit"])
        assert storage.list_keys(_THUMBNAILS, "") == [f"{_ACTIVITY}.webp"]
        assert storage.list_keys(_MEDIA, "") == [f"{_ACTIVITY}_aaa.jpg", f"{_ACTIVITY}_bbb.jpg"]
        assert storage.get(_MEDIA, f"{_ACTIVITY}_bbb.jpg") == b"bbb"
        assert _stored_paths(db) == ([None, f"{_ACTIVITY}.webp"], [f"{_ACTIVITY}_aaa.jpg", f"{_ACTIVITY}_bbb.jpg"])
        assert _executed(db) is True

    def test_an_existing_uuid_key_is_not_overwritten(self, storage: S3Storage, db: Session):
        storage.save(_MEDIA, "1_aaa.jpg", b"old", "image/jpeg")
        storage.save(_MEDIA, f"{_ACTIVITY}_aaa.jpg", b"already copied", "image/jpeg")

        _run(storage, db)

        assert storage.get(_MEDIA, f"{_ACTIVITY}_aaa.jpg") == b"already copied"
        assert storage.list_keys(_MEDIA, "") == [f"{_ACTIVITY}_aaa.jpg"]

    def test_a_failing_copy_leaves_the_columns_and_the_integer_blobs_and_the_next_run_finishes(
        self, storage: S3Storage, client: _FakeS3Client, db: Session
    ):
        client.fail_copy_to = f"{_ACTIVITY}_bbb.jpg"
        _save_activity_blobs(storage)

        _run(storage, db)

        assert _executed(db) is False
        assert _table_exists(db) is True
        assert _stored_paths(db)[1] == ["1_aaa.jpg", "1_bbb.jpg"]
        assert storage.list_keys(_MEDIA, "") == sorted(
            ["1_aaa.jpg", "1_bbb.jpg", "999_eee.jpg", f"{_ACTIVITY}_aaa.jpg"]
        )

        client.fail_copy_to = None
        _run(storage, db)

        assert storage.list_keys(_MEDIA, "") == [f"{_ACTIVITY}_aaa.jpg", f"{_ACTIVITY}_bbb.jpg"]
        assert _stored_paths(db)[1] == [f"{_ACTIVITY}_aaa.jpg", f"{_ACTIVITY}_bbb.jpg"]
        assert _executed(db) is True

    def test_a_second_run_changes_nothing(self, storage: S3Storage, db: Session):
        _save_activity_blobs(storage)
        _run(storage, db)
        paths = _stored_paths(db)

        _record_the_ids_again(db)

        _run(storage, db)

        assert _stored_paths(db) == paths
        assert storage.list_keys(_MEDIA, "") == [f"{_ACTIVITY}_aaa.jpg", f"{_ACTIVITY}_bbb.jpg"]


def _photo_paths(db: Session) -> dict[uuid.UUID, str | None]:
    db.rollback()
    return dict(db.execute(sa.select(users_models.Users.id, users_models.Users.photo_path)).tuples().all())


def _save_user_blobs(storage: LocalStorage | S3Storage) -> None:
    storage.save(_PHOTOS, "1.jpg", b"photo", "image/jpeg")
    storage.save(_PHOTOS, "2.png", b"unnamed photo", "image/png")
    storage.save(_PHOTOS, "999.jpg", b"orphan", "image/jpeg")
    storage.save(_IMPORT_ERRORS, "1/bad.fit", b"bad", "application/octet-stream")
    storage.save(_IMPORT_ERRORS, "1/sub/worse.fit", b"worse", "application/octet-stream")
    storage.save(_IMPORT_ERRORS, "999/bad.fit", b"orphan", "application/octet-stream")
    storage.save(_EXPORTS, "1.zip", b"export", "application/zip")
    storage.save(_EXPORTS, "999.zip", b"orphan", "application/zip")
    storage.save(_IMPORTS, "2/archive.zip", b"import", "application/zip")
    storage.save(_IMPORTS, "999/archive.zip", b"orphan", "application/zip")


def _assert_user_blobs_renamed(storage: LocalStorage | S3Storage, db: Session) -> None:
    assert storage.list_keys(_PHOTOS, "") == sorted([f"{_OTHER_USER}.png", f"{_USER}.jpg"])
    assert storage.get(_PHOTOS, f"{_USER}.jpg") == b"photo"
    assert storage.list_keys(_IMPORT_ERRORS, "") == [f"{_USER}/bad.fit", f"{_USER}/sub/worse.fit"]
    assert storage.get(_IMPORT_ERRORS, f"{_USER}/sub/worse.fit") == b"worse"
    assert storage.list_keys(_EXPORTS, "") == [f"{_USER}.zip"]
    assert storage.get(_EXPORTS, f"{_USER}.zip") == b"export"
    assert storage.list_keys(_IMPORTS, "") == [f"{_OTHER_USER}/archive.zip"]
    assert _photo_paths(db) == {_USER: f"{_USER}.jpg", _OTHER_USER: "https://example.org/2.jpg"}
    assert _executed(db) is True


class TestUserBlobs:
    @pytest.fixture(autouse=True)
    def _drop_folders(self, tmp_path: Path):
        with (
            patch.object(core_config, "FILES_BULK_IMPORT_DIR", str(tmp_path / "files/bulk_import")),
            patch.object(core_config.settings, "FILES_DIR", str(tmp_path / "files")),
        ):
            yield

    def test_renames_the_photos_errors_and_staged_archives_and_rewrites_photo_path(self, tmp_path: Path, db: Session):
        storage = LocalStorage(str(tmp_path / "storage"))
        _save_user_blobs(storage)

        _run(storage, db)

        _assert_user_blobs_renamed(storage, db)

    def test_a_failing_photo_copy_leaves_photo_path_and_the_integer_photo_and_the_next_run_finishes(
        self, tmp_path: Path, db: Session
    ):
        storage = _FailingCopy(str(tmp_path / "storage"))
        storage.fail = "1.jpg"
        _save_user_blobs(storage)

        _run(storage, db)

        assert _executed(db) is False
        assert _photo_paths(db)[_USER] == "1.jpg"
        assert storage.get(_PHOTOS, "1.jpg") == b"photo"

        storage.fail = ""
        _run(storage, db)

        _assert_user_blobs_renamed(storage, db)

    def test_an_existing_uuid_key_is_not_overwritten(self, tmp_path: Path, db: Session):
        storage = LocalStorage(str(tmp_path / "storage"))
        storage.save(_PHOTOS, "1.jpg", b"old", "image/jpeg")
        storage.save(_PHOTOS, f"{_USER}.jpg", b"already copied", "image/jpeg")
        storage.save(_EXPORTS, "1.zip", b"old", "application/zip")
        storage.save(_EXPORTS, f"{_USER}.zip", b"already copied", "application/zip")

        _run(storage, db)

        assert storage.list_keys(_PHOTOS, "") == [f"{_USER}.jpg"]
        assert storage.get(_PHOTOS, f"{_USER}.jpg") == b"already copied"
        assert storage.get(_EXPORTS, f"{_USER}.zip") == b"already copied"

    def test_a_second_run_changes_nothing(self, tmp_path: Path, db: Session):
        storage = LocalStorage(str(tmp_path / "storage"))
        _save_user_blobs(storage)
        _run(storage, db)

        _record_the_ids_again(db)

        _run(storage, db)

        _assert_user_blobs_renamed(storage, db)

    def test_renames_the_blobs_on_s3(self, db: Session):
        storage = S3Storage(_FakeS3Client(), "bucket", "endurain")
        _save_user_blobs(storage)

        _run(storage, db)

        _assert_user_blobs_renamed(storage, db)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


class TestUserDropFolders:
    @pytest.fixture(autouse=True)
    def _drop_folders(self, tmp_path: Path):
        with (
            patch.object(core_config, "FILES_BULK_IMPORT_DIR", str(tmp_path / "files/bulk_import")),
            patch.object(core_config.settings, "FILES_DIR", str(tmp_path / "files")),
        ):
            yield

    def test_renames_both_folders_and_keeps_the_folder_of_a_deleted_user(self, tmp_path: Path, db: Session):
        files = tmp_path / "files"
        _write(files / "bulk_import/1/nested/a.fit", "a")
        _write(files / "bulk_import/999/orphan.fit", "orphan")
        _write(files / "strava_import/2/activities.csv", "csv")
        _write(files / "bulk_import/not-a-user/kept.fit", "kept")

        _run(LocalStorage(str(tmp_path / "storage")), db)

        assert (files / f"bulk_import/{_USER}/nested/a.fit").read_text() == "a"
        assert (files / f"strava_import/{_OTHER_USER}/activities.csv").read_text() == "csv"
        assert not (files / "bulk_import/1").exists()
        assert not (files / "strava_import/2").exists()
        assert (files / "bulk_import/999/orphan.fit").read_text() == "orphan"
        assert (files / "bulk_import/not-a-user/kept.fit").read_text() == "kept"
        assert _executed(db) is True

    def test_merges_into_an_existing_folder_and_keeps_a_conflicting_file(self, tmp_path: Path, db: Session):
        files = tmp_path / "files"
        _write(files / f"bulk_import/{_USER}/same.fit", "new")
        _write(files / f"bulk_import/{_USER}/own.fit", "own")
        _write(files / "bulk_import/1/same.fit", "old")
        _write(files / "bulk_import/1/moved.fit", "moved")
        _write(files / "bulk_import/1/sub/deep.fit", "deep")

        _run(LocalStorage(str(tmp_path / "storage")), db)

        target = files / f"bulk_import/{_USER}"
        assert (target / "same.fit").read_text() == "new"
        assert (target / "own.fit").read_text() == "own"
        assert (target / "moved.fit").read_text() == "moved"
        assert (target / "sub/deep.fit").read_text() == "deep"
        assert (files / "bulk_import/1/same.fit").read_text() == "old"
        assert not (files / "bulk_import/1/moved.fit").exists()
        assert not (files / "bulk_import/1/sub").exists()
        assert _executed(db) is True

    def test_a_folder_that_cannot_be_moved_keeps_the_migration_pending_and_the_next_run_finishes(
        self, tmp_path: Path, db: Session
    ):
        files = tmp_path / "files"
        _write(files / "bulk_import/1/a.fit", "a")
        storage = LocalStorage(str(tmp_path / "storage"))

        with patch(f"{_MODULE}.os.rename", side_effect=OSError("denied")):
            _run(storage, db)

        assert _executed(db) is False
        assert _table_exists(db) is True
        assert (files / "bulk_import/1/a.fit").read_text() == "a"

        _run(storage, db)

        assert (files / f"bulk_import/{_USER}/a.fit").read_text() == "a"
        assert _executed(db) is True

    def test_a_second_run_changes_nothing(self, tmp_path: Path, db: Session):
        files = tmp_path / "files"
        _write(files / "strava_import/1/a.csv", "a")
        storage = LocalStorage(str(tmp_path / "storage"))
        _run(storage, db)

        _record_the_ids_again(db)

        _run(storage, db)

        assert (files / f"strava_import/{_USER}/a.csv").read_text() == "a"
        assert _executed(db) is True

    def test_an_unreadable_root_keeps_the_migration_pending_and_the_next_run_finishes(
        self, tmp_path: Path, db: Session
    ):
        files = tmp_path / "files"
        _write(files / "bulk_import/1/a.fit", "a")
        storage = LocalStorage(str(tmp_path / "storage"))
        root = files / "bulk_import"
        root.chmod(0o000)
        try:
            _run(storage, db)
        finally:
            root.chmod(0o755)

        assert _executed(db) is False
        assert _table_exists(db) is True
        assert (files / "bulk_import/1/a.fit").read_text() == "a"

        _run(storage, db)

        assert (files / f"bulk_import/{_USER}/a.fit").read_text() == "a"
        assert _executed(db) is True

    def test_an_unreadable_subfolder_keeps_the_migration_pending_and_the_next_run_finishes(
        self, tmp_path: Path, db: Session
    ):
        files = tmp_path / "files"
        _write(files / f"bulk_import/{_USER}/own.fit", "own")
        _write(files / "bulk_import/1/top.fit", "top")
        _write(files / "bulk_import/1/sub/deep.fit", "deep")
        storage = LocalStorage(str(tmp_path / "storage"))
        subfolder = files / "bulk_import/1/sub"
        subfolder.chmod(0o000)
        try:
            _run(storage, db)
        finally:
            subfolder.chmod(0o755)

        assert _executed(db) is False
        assert _table_exists(db) is True
        assert (subfolder / "deep.fit").read_text() == "deep"

        _run(storage, db)

        assert (files / f"bulk_import/{_USER}/sub/deep.fit").read_text() == "deep"
        assert (files / f"bulk_import/{_USER}/top.fit").read_text() == "top"
        assert not (files / "bulk_import/1").exists()
        assert _executed(db) is True


class TestStateIsLeftAlone:
    def test_a_failed_run_and_its_retry_never_clear_the_state(self, tmp_path: Path, db: Session):
        storage = _FailingCopy(str(tmp_path))
        storage.fail = "1"
        storage.save(_AREA, "1", b"first", "image/png")

        with patch(f"{_MODULE}.platform_runtime") as runtime:
            runtime.get_active_platform.return_value.storage = storage
            migration_13.process_migration_13(db)
            storage.fail = ""
            migration_13.process_migration_13(db)

        runtime.get_active_platform.return_value.state.delete_prefix.assert_not_called()
        assert _executed(db) is True
