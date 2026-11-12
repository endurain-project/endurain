"""Tests for the activity media service (authorization, storage, cleanup)."""

import io
import uuid
from unittest.mock import MagicMock, patch

import jasil.providers as platform_providers
import pytest
from fastapi import UploadFile
from tests._helpers import images

import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import core.hashing as core_hashing

ACT = uuid.UUID("00000000-0000-4000-8000-000000000001")
ACT42 = uuid.UUID("00000000-0000-4000-8000-000000000042")
OTHER = uuid.UUID("00000000-0000-4000-8000-000000000099")
M2 = uuid.UUID("00000000-0000-4000-8000-0000000000a2")
M3 = uuid.UUID("00000000-0000-4000-8000-0000000000a3")
M4 = uuid.UUID("00000000-0000-4000-8000-0000000000a4")
M5 = uuid.UUID("00000000-0000-4000-8000-0000000000a5")
M9 = uuid.UUID("00000000-0000-4000-8000-0000000000a9")

_SVC = "modules.activities.activity_media.service"
_JPEG = images.jpeg_with_exif()


def _read_jpeg() -> bytes:
    """The upload reader the service is handed."""
    return _JPEG


class TestBuildStorageKey:
    def test_generates_server_side_key_with_allowed_extension(self):
        from modules.activities.activity_media.service import _build_storage_key

        key = _build_storage_key(ACT42, "holiday photo.JPG")

        assert key.startswith(f"{ACT42}_")
        assert key.endswith(".jpg")
        # The original stem never survives, so a hostile name cannot be echoed back.
        assert "holiday" not in key

    def test_strips_directory_components(self):
        from modules.activities.activity_media.service import _build_storage_key

        key = _build_storage_key(ACT, "../../etc/passwd.png")

        assert "/" not in key
        assert key.endswith(".png")

    def test_rejects_disallowed_extension(self):
        from modules.activities.activity_media.service import _build_storage_key

        with pytest.raises(core_exceptions.UnsupportedMediaTypeError) as exc:
            _build_storage_key(ACT, "payload.svg")
        assert exc.value.status_code == 415

    def test_rejects_missing_filename(self):
        from modules.activities.activity_media.service import _build_storage_key

        with pytest.raises(core_exceptions.UnsupportedMediaTypeError) as exc:
            _build_storage_key(ACT, None)
        assert exc.value.status_code == 415


class TestRekeyMediaPath:
    def test_re_addresses_a_key_named_by_the_archived_key_text(self):
        from modules.activities.activity_media.service import rekey_media_path

        assert rekey_media_path("17_abc.jpg", "17", ACT) == f"{ACT}_abc.jpg"
        assert rekey_media_path(f"{OTHER}_abc.jpg", str(OTHER), ACT) == f"{ACT}_abc.jpg"

    def test_a_key_of_another_activity_is_refused(self):
        from modules.activities.activity_media.service import rekey_media_path

        assert rekey_media_path("18_abc.jpg", "17", ACT) is None
        assert rekey_media_path("abc.jpg", "17", ACT) is None

    @pytest.mark.parametrize("old_key", ["17_", "17_a/b.jpg", "17_a\\b.jpg", "17_../x.jpg"])
    def test_a_suffix_that_is_not_a_flat_file_name_is_refused(self, old_key):
        from modules.activities.activity_media.service import rekey_media_path

        assert rekey_media_path(old_key, "17", ACT) is None


class TestSweepOrphanedMedia:
    @patch(f"{_SVC}.core_blob_sweep.sweep_unreferenced_blobs", return_value=0)
    @patch(f"{_SVC}.activity_integration")
    @patch("core.blob_sweep.core_database")
    def test_a_uuid_key_whose_activity_is_gone_is_swept_and_an_integer_key_is_kept(
        self, _database, mock_activities, _unreferenced
    ):
        from modules.activities.activity_media.service import sweep_orphaned_media

        mock_activities.filter_existing_activity_ids.return_value = set()
        storage = MagicMock()
        storage.iter_objects.return_value = iter([(f"{ACT}_a.jpg", 0.0), ("42_x.jpg", 0.0)])

        assert sweep_orphaned_media(storage) == 1

        storage.delete.assert_called_once_with("activity_media", f"{ACT}_a.jpg")


class TestListActivityMedia:
    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_returns_media_for_owned_activity(self, mock_activities_service, mock_media_crud):
        from modules.activities.activity_media.contracts import ActivityMediaRecord
        from modules.activities.activity_media.service import list_activity_media

        mock_activities_service.owns_activity.return_value = True
        mock_media_crud.get_media_for_activity.return_value = [
            ActivityMediaRecord(id=M3, activity_id=ACT, media_path=f"{ACT}_abc.jpg", media_type=1)
        ]
        mock_media_crud.count_media_for_activity.return_value = 1

        page = list_activity_media(ACT, 2, MagicMock())

        # The storage key never reaches the caller; a servable URL does.
        assert page.total == 1
        assert len(page.items) == 1
        assert not hasattr(page.items[0], "media_path")
        assert f"/activities/{ACT}/media/{M3}/file?t=" in page.items[0].url

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_returns_empty_when_activity_not_owned(self, mock_activities_service, mock_media_crud):
        from modules.activities.activity_media.service import list_activity_media

        mock_activities_service.owns_activity.return_value = False

        page = list_activity_media(ACT, 2, MagicMock())

        assert page.items == []
        assert page.total == 0
        mock_media_crud.get_media_for_activity.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_returns_empty_when_no_media(self, mock_activities_service, mock_media_crud):
        from modules.activities.activity_media.service import list_activity_media

        mock_activities_service.owns_activity.return_value = True
        mock_media_crud.get_media_for_activity.return_value = []
        mock_media_crud.count_media_for_activity.return_value = 0

        assert list_activity_media(ACT, 2, MagicMock()).items == []


class TestStoreActivityMedia:
    @patch(f"{_SVC}.activity_integration")
    def test_an_activity_that_is_not_the_callers_is_refused_before_the_upload_is_read(self, mock_activities_service):
        from modules.activities.activity_media.service import store_activity_media

        mock_activities_service.owns_activity.return_value = False
        storage, read_upload = MagicMock(), MagicMock()

        with pytest.raises(core_exceptions.NotFoundError):
            store_activity_media(ACT, 2, "ride.jpg", read_upload, storage, MagicMock())

        read_upload.assert_not_called()
        storage.save.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_saves_blob_and_creates_record(self, mock_activities_service, mock_media_crud):
        from modules.activities.activity_media.contracts import ActivityMediaRecord
        from modules.activities.activity_media.service import store_activity_media

        mock_activities_service.owns_activity.return_value = True
        storage = MagicMock()
        mock_media_crud.get_activity_media_by_content_hash.return_value = None
        mock_media_crud.create_activity_media.return_value = ActivityMediaRecord(
            id=M9, activity_id=ACT, media_path=f"{ACT}_abc.jpg", media_type=1
        )

        result = store_activity_media(ACT, 2, "ride.jpg", _read_jpeg, storage, MagicMock())

        assert result.id == M9
        assert f"/activities/{ACT}/media/{M9}/file?t=" in result.url
        area, key, data, content_type = storage.save.call_args.args
        assert area == "activity_media"
        assert key.startswith(f"{ACT}_") and key.endswith(".jpg")
        assert not images.has_metadata(data)
        # Derived from the validated extension: the client's Content-Type header
        # must never reach the storage backend as object metadata.
        assert content_type == "image/jpeg"
        # The row records the storage key, never a filesystem path.
        assert mock_media_crud.create_activity_media.call_args.args[1] == key
        # ... and the bytes' hash, so a later re-store of the same photo no-ops.
        assert mock_media_crud.create_activity_media.call_args.kwargs["content_hash"]

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_returns_existing_record_without_storing_when_content_matches(
        self, mock_activities_service, mock_media_crud
    ):
        """A retried upload of the exact same photo must not create a second row."""
        from modules.activities.activity_media.contracts import ActivityMediaRecord
        from modules.activities.activity_media.service import store_activity_media

        mock_activities_service.owns_activity.return_value = True
        storage = MagicMock()
        existing = ActivityMediaRecord(id=M4, activity_id=ACT, media_path=f"{ACT}_existing.jpg", media_type=1)
        mock_media_crud.get_activity_media_by_content_hash.return_value = existing

        result = store_activity_media(ACT, 2, "ride.jpg", _read_jpeg, storage, MagicMock())

        assert result.id == M4
        storage.save.assert_not_called()
        mock_media_crud.create_activity_media.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_rejects_activity_owned_by_another_user(self, mock_activities_service, mock_media_crud):
        from modules.activities.activity_media.service import store_activity_media

        mock_activities_service.owns_activity.return_value = False

        with pytest.raises(core_exceptions.NotFoundError) as exc:
            storage = MagicMock()
            store_activity_media(ACT, 2, "ride.jpg", _read_jpeg, storage, MagicMock())

        assert exc.value.status_code == 404
        # Nothing is stored for an activity the caller does not own.
        storage.save.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_removes_blob_when_record_creation_fails(self, mock_activities_service, mock_media_crud):
        from modules.activities.activity_media.service import store_activity_media

        mock_activities_service.owns_activity.return_value = True
        storage = MagicMock()
        mock_media_crud.get_activity_media_by_content_hash.return_value = None
        mock_media_crud.create_activity_media.side_effect = core_exceptions.ConflictError("dup")

        with pytest.raises(core_exceptions.ConflictError):
            store_activity_media(ACT, 2, "ride.jpg", _read_jpeg, storage, MagicMock())

        # A failed upload leaves no orphaned blob.
        stored_key = storage.save.call_args.args[1]
        storage.delete.assert_called_once_with("activity_media", stored_key)

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_removes_blob_when_the_commit_fails(self, mock_activities_service, mock_media_crud):
        """A database failure that is not a domain error still leaves no orphan blob."""
        from sqlalchemy.exc import OperationalError

        from modules.activities.activity_media.service import store_activity_media

        mock_activities_service.owns_activity.return_value = True
        storage = MagicMock()
        db = MagicMock()
        # The first commit ends the duplicate check's transaction; the second stores the row.
        db.commit.side_effect = [None, OperationalError("stmt", {}, Exception("connection lost"))]
        mock_media_crud.get_activity_media_by_content_hash.return_value = None

        with pytest.raises(OperationalError):
            store_activity_media(ACT, 2, "ride.jpg", _read_jpeg, storage, db)

        stored_key = storage.save.call_args.args[1]
        storage.delete.assert_called_once_with("activity_media", stored_key)

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_race_lost_to_a_concurrent_store_returns_the_winner(self, mock_activities_service, mock_media_crud):
        """The pre-check is read-then-write; losing the race to the unique index
        must return the winner rather than surfacing a conflict for what the
        caller experiences as a successful store."""
        from modules.activities.activity_media.contracts import ActivityMediaRecord
        from modules.activities.activity_media.service import store_activity_media

        mock_activities_service.owns_activity.return_value = True
        storage = MagicMock()
        winner = ActivityMediaRecord(id=M4, activity_id=ACT, media_path=f"{ACT}_winner.jpg", media_type=1)
        # Miss on the pre-check, then find the winner once the insert conflicts.
        mock_media_crud.get_activity_media_by_content_hash.side_effect = [None, winner]
        mock_media_crud.create_activity_media.side_effect = core_exceptions.ConflictError("dup")

        result = store_activity_media(ACT, 2, "ride.jpg", _read_jpeg, storage, MagicMock())

        assert result.id == M4
        stored_key = storage.save.call_args.args[1]
        storage.delete.assert_called_once_with("activity_media", stored_key)

    @patch(f"{_SVC}.activity_media_crud")
    def test_a_lost_race_rolls_back_before_looking_up_the_winner(self, mock_media_crud):
        """A failed flush leaves the session unusable until it is rolled back, so
        the winner lookup has to come after the rollback."""
        from modules.activities.activity_media.contracts import ActivityMediaRecord
        from modules.activities.activity_media.service import store_activity_media_bytes

        events: list[str] = []
        db = MagicMock()
        db.rollback.side_effect = lambda: events.append("rollback")
        winner = ActivityMediaRecord(id=M4, activity_id=ACT, media_path=f"{ACT}_winner.jpg", media_type=1)

        def lookup(*_args, **_kwargs):
            events.append("lookup")
            return None if events.count("lookup") == 1 else winner

        mock_media_crud.get_activity_media_by_content_hash.side_effect = lookup
        mock_media_crud.create_activity_media.side_effect = core_exceptions.ConflictError("dup")

        result = store_activity_media_bytes(ACT, "photo.jpg", _JPEG, MagicMock(), db)

        assert result.id == M4
        assert events == ["lookup", "rollback", "lookup"]
        # Only the commit that ended the duplicate check's transaction; the row was never stored.
        db.commit.assert_called_once()

    @patch(f"{_SVC}.activity_integration")
    @patch(f"{_SVC}.activity_media_crud")
    def test_a_successful_store_commits(self, mock_media_crud, mock_activity_integration):
        from modules.activities.activity_media.contracts import ActivityMediaRecord
        from modules.activities.activity_media.service import store_activity_media_bytes

        db = MagicMock()
        mock_media_crud.get_activity_media_by_content_hash.return_value = None
        mock_media_crud.create_activity_media.return_value = ActivityMediaRecord(
            id=M9, activity_id=ACT, media_path=f"{ACT}_abc.jpg", media_type=1
        )

        store_activity_media_bytes(ACT, "photo.jpg", _JPEG, MagicMock(), db)

        # One commit ends the duplicate check before the blob is written, one stores the row.
        assert db.commit.call_count == 2
        mock_activity_integration.touch_activity.assert_called_once_with(ACT, db)


class TestStoredMediaMetadata:
    @patch(f"{_SVC}.activity_media_crud")
    def test_the_hash_covers_the_original_bytes_while_the_blob_is_stripped(self, mock_media_crud):
        """A re-run import of the same original photo is still recognised as a duplicate."""
        from modules.activities.activity_media.contracts import ActivityMediaRecord
        from modules.activities.activity_media.service import store_activity_media_bytes

        storage = MagicMock()
        mock_media_crud.get_activity_media_by_content_hash.return_value = None
        mock_media_crud.create_activity_media.return_value = ActivityMediaRecord(
            id=M9, activity_id=ACT, media_path=f"{ACT}_abc.jpg", media_type=1
        )

        store_activity_media_bytes(ACT, "photo.jpg", _JPEG, storage, MagicMock())

        stored = storage.save.call_args.args[2]
        assert stored != _JPEG
        assert not images.has_metadata(stored)
        assert mock_media_crud.get_activity_media_by_content_hash.call_args.args[1] == core_hashing.sha256_hex(_JPEG)
        assert mock_media_crud.create_activity_media.call_args.kwargs["content_hash"] == core_hashing.sha256_hex(_JPEG)

    @patch(f"{_SVC}.activity_media_crud")
    def test_an_undecodable_image_stores_nothing(self, mock_media_crud):
        from modules.activities.activity_media.service import store_activity_media_bytes

        storage = MagicMock()
        mock_media_crud.get_activity_media_by_content_hash.return_value = None

        with pytest.raises(core_exceptions.InvalidInputError):
            store_activity_media_bytes(ACT, "photo.jpg", b"not an image", storage, MagicMock())

        storage.save.assert_not_called()
        mock_media_crud.create_activity_media.assert_not_called()


class TestStoreActivityMediaBytes:
    """The server-side ingestion counterpart (Strava bulk-export sidecar photos)."""

    @patch(f"{_SVC}.activity_media_crud")
    def test_saves_blob_and_creates_record(self, mock_media_crud):
        from modules.activities.activity_media.contracts import ActivityMediaRecord
        from modules.activities.activity_media.service import store_activity_media_bytes

        storage = MagicMock()
        mock_media_crud.get_activity_media_by_content_hash.return_value = None
        mock_media_crud.create_activity_media.return_value = ActivityMediaRecord(
            id=M9, activity_id=ACT, media_path=f"{ACT}_abc.jpg", media_type=1
        )

        result = store_activity_media_bytes(ACT, "photo.jpg", _JPEG, storage, MagicMock())

        assert result.id == M9
        area, _key, data, content_type = storage.save.call_args.args
        assert area == "activity_media"
        assert not images.has_metadata(data)
        assert content_type == "image/jpeg"
        assert mock_media_crud.create_activity_media.call_args.kwargs["content_hash"]

    @patch(f"{_SVC}.activity_media_crud")
    def test_re_running_a_bulk_import_does_not_duplicate_the_photo(self, mock_media_crud):
        """A Strava bulk-export re-run must not create a second media row for a
        photo it already imported for this activity."""
        from modules.activities.activity_media.contracts import ActivityMediaRecord
        from modules.activities.activity_media.service import store_activity_media_bytes

        storage = MagicMock()
        existing = ActivityMediaRecord(id=M4, activity_id=ACT, media_path=f"{ACT}_existing.jpg", media_type=1)
        mock_media_crud.get_activity_media_by_content_hash.return_value = existing

        result = store_activity_media_bytes(ACT, "photo.jpg", _JPEG, storage, MagicMock())

        assert result.id == M4
        storage.save.assert_not_called()
        mock_media_crud.create_activity_media.assert_not_called()


class TestDeleteActivityMedia:
    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_deletes_record_and_blob(self, mock_activities_service, mock_media_crud):
        from modules.activities.activity_media.service import delete_activity_media

        mock_media_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=ACT, media_path=f"{ACT}_abc.jpg")
        mock_activities_service.owns_activity.return_value = True

        storage = MagicMock()
        db = MagicMock()
        delete_activity_media(ACT, M5, 2, storage, db)

        mock_media_crud.delete_activity_media.assert_called_once()
        mock_activities_service.touch_activity.assert_called_once_with(ACT, db)
        storage.delete.assert_called_once_with("activity_media", f"{ACT}_abc.jpg")

    @patch(f"{_SVC}.activity_media_crud")
    def test_missing_media_is_404(self, mock_media_crud):
        from modules.activities.activity_media.service import delete_activity_media

        mock_media_crud.get_activity_media_by_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError) as exc:
            storage = MagicMock()
            delete_activity_media(ACT, M5, 2, storage, MagicMock())
        assert exc.value.status_code == 404

    @patch(f"{_SVC}.activity_media_crud")
    def test_media_belonging_to_another_activity_is_404(self, mock_media_crud):
        """The media id must match the activity in the route path.

        Now that the route is ``/activities/{activity_id}/media/{media_id}``, a
        media id reached through an unrelated activity's URL must not resolve —
        otherwise the path would claim a relationship the handler never checked.
        """
        from modules.activities.activity_media.service import delete_activity_media

        mock_media_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=OTHER, media_path="/media/x.jpg")

        with pytest.raises(core_exceptions.NotFoundError) as exc:
            storage = MagicMock()
            delete_activity_media(ACT, M5, 2, storage, MagicMock())

        assert exc.value.status_code == 404
        mock_media_crud.delete_activity_media.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_media_on_another_users_activity_is_404(self, mock_activities_service, mock_media_crud):
        from modules.activities.activity_media.service import delete_activity_media

        mock_media_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=ACT, media_path="/media/x.jpg")
        mock_activities_service.owns_activity.return_value = False

        with pytest.raises(core_exceptions.NotFoundError) as exc:
            storage = MagicMock()
            delete_activity_media(ACT, M5, 2, storage, MagicMock())

        assert exc.value.status_code == 404
        # 404 rather than 403 so media ids cannot be probed, and nothing is deleted.
        mock_media_crud.delete_activity_media.assert_not_called()

    @patch(f"{_SVC}.logger")
    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_cleanup_failure_is_logged_not_raised(self, mock_activities_service, mock_media_crud, mock_logger):
        from modules.activities.activity_media.service import delete_activity_media

        mock_media_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=ACT, media_path=f"{ACT}_abc.jpg")
        mock_activities_service.owns_activity.return_value = True
        storage = MagicMock()
        storage.delete.side_effect = platform_providers.StorageBackendUnavailableError("backend down")

        delete_activity_media(ACT, M5, 2, storage, MagicMock())

        # The row is still gone; only the blob cleanup failed.
        mock_media_crud.delete_activity_media.assert_called_once()
        mock_logger.warning.assert_called_once()


class TestNoConnectionHeldWhileUsingStorage:
    """A read leaves the session holding a pooled connection, so the blob is moved only after it has ended."""

    def test_storing_media_commits_the_duplicate_check_before_the_blob_is_written(self):
        from modules.activities.activity_media import service

        db = MagicMock()
        storage = MagicMock()
        order = MagicMock()
        order.attach_mock(db.commit, "commit")
        order.attach_mock(storage.save, "save")
        storage.save.side_effect = RuntimeError("stop here")

        with (
            patch(f"{_SVC}.activity_media_crud.get_activity_media_by_content_hash", return_value=None),
            pytest.raises(RuntimeError, match="stop here"),
        ):
            service._persist_media_bytes(ACT, "a.jpg", _JPEG, storage, db)

        assert [call[0] for call in order.mock_calls] == ["commit", "save"]

    def test_serving_media_ends_the_read_before_the_blob_is_fetched(self):
        from modules.activities.activity_media import service

        db = MagicMock()
        storage = MagicMock()
        storage.get.return_value = b"image"
        order = MagicMock()
        order.attach_mock(db.commit, "commit")
        order.attach_mock(storage.get, "get")

        with (
            patch(f"{_SVC}.activity_media_signing.verify_media_token", return_value=True),
            patch(
                f"{_SVC}.activity_media_crud.get_activity_media_by_id",
                return_value=MagicMock(activity_id=ACT, media_path=f"{ACT}_x.jpg"),
            ),
        ):
            service.read_activity_media_blob(ACT, M2, "token", storage, db)

        assert [call[0] for call in order.mock_calls] == ["commit", "get"]


class TestImageFormats:
    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("1_a.jpg", "image/jpeg"),
            ("1_a.JPEG", "image/jpeg"),
            ("1_a.png", "image/png"),
            ("1_a.webp", "image/webp"),
            ("1_a.heic", "application/octet-stream"),
        ],
    )
    def test_a_stored_key_is_served_with_the_type_of_its_extension(self, key, expected):
        from modules.activities.activity_media.service import _content_type_for

        assert _content_type_for(key) == expected

    @pytest.mark.parametrize("name", ["a.gif", "a.heic", "a.heif"])
    def test_gif_and_heic_names_are_refused(self, name):
        from modules.activities.activity_media.service import _build_storage_key

        with pytest.raises(core_exceptions.UnsupportedMediaTypeError):
            _build_storage_key(ACT, name)

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_a_webp_is_stored_without_its_metadata(self, mock_activities_service, mock_media_crud):
        from modules.activities.activity_media.contracts import ActivityMediaRecord
        from modules.activities.activity_media.service import store_activity_media

        mock_activities_service.owns_activity.return_value = True
        mock_media_crud.get_activity_media_by_content_hash.return_value = None
        mock_media_crud.create_activity_media.return_value = ActivityMediaRecord(
            id=M9, activity_id=ACT, media_path=f"{ACT}_abc.webp", media_type=1
        )
        storage = MagicMock()
        webp = images.webp_with_exif()

        store_activity_media(
            ACT,
            2,
            "ride.webp",
            lambda: core_file_uploads.read_validated_upload_sync(
                UploadFile(io.BytesIO(webp), filename="ride.webp"), kind=core_file_uploads.UploadKind.IMAGE
            ),
            storage,
            MagicMock(),
        )

        _area, key, data, content_type = storage.save.call_args.args
        assert key.endswith(".webp")
        assert content_type == "image/webp"
        assert not images.has_metadata(data)

    @pytest.mark.parametrize(
        ("name", "data"), [("a.gif", images.gif()), ("a.heic", images.heic_like())], ids=["gif", "heic"]
    )
    def test_gif_and_heic_uploads_are_refused_by_the_validator(self, name, data):
        with pytest.raises(core_exceptions.DomainError) as exc:
            core_file_uploads.read_validated_upload_sync(
                UploadFile(io.BytesIO(data), filename=name), kind=core_file_uploads.UploadKind.IMAGE
            )

        assert exc.value.status_code == 415
