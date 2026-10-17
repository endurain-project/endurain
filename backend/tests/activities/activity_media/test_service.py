"""Tests for the activity media service (authorization, storage, cleanup)."""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions

_SVC = "modules.activities.activity_media.service"


class TestBuildStorageKey:
    def test_generates_server_side_key_with_allowed_extension(self):
        from modules.activities.activity_media.service import _build_storage_key

        key = _build_storage_key(42, "holiday photo.JPG")

        assert key.startswith("42_")
        assert key.endswith(".jpg")
        # The original stem never survives, so a hostile name cannot be echoed back.
        assert "holiday" not in key

    def test_strips_directory_components(self):
        from modules.activities.activity_media.service import _build_storage_key

        key = _build_storage_key(1, "../../etc/passwd.png")

        assert "/" not in key
        assert key.endswith(".png")

    def test_rejects_disallowed_extension(self):
        from modules.activities.activity_media.service import _build_storage_key

        with pytest.raises(core_exceptions.UnsupportedMediaTypeError) as exc:
            _build_storage_key(1, "payload.svg")
        assert exc.value.status_code == 415

    def test_rejects_missing_filename(self):
        from modules.activities.activity_media.service import _build_storage_key

        with pytest.raises(core_exceptions.UnsupportedMediaTypeError) as exc:
            _build_storage_key(1, None)
        assert exc.value.status_code == 415


class TestListActivityMedia:
    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_returns_media_for_owned_activity(self, mock_activities_service, mock_media_crud):
        from modules.activities.activity_media.contracts import ActivityMediaRecord
        from modules.activities.activity_media.service import list_activity_media

        mock_activities_service.owns_activity.return_value = True
        mock_media_crud.get_media_for_activity.return_value = [
            ActivityMediaRecord(id=3, activity_id=1, media_path="1_abc.jpg", media_type=1)
        ]
        mock_media_crud.count_media_for_activity.return_value = 1

        page = list_activity_media(1, 2, MagicMock())

        # The storage key never reaches the caller; a servable URL does.
        assert page.total == 1
        assert len(page.items) == 1
        assert not hasattr(page.items[0], "media_path")
        assert "/activities/1/media/3/file?t=" in page.items[0].url

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_returns_empty_when_activity_not_owned(self, mock_activities_service, mock_media_crud):
        from modules.activities.activity_media.service import list_activity_media

        mock_activities_service.owns_activity.return_value = False

        page = list_activity_media(1, 2, MagicMock())

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

        assert list_activity_media(1, 2, MagicMock()).items == []


class TestStoreActivityMedia:
    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_saves_blob_and_creates_record(self, mock_activities_service, mock_media_crud):
        from modules.activities.activity_media.contracts import ActivityMediaRecord
        from modules.activities.activity_media.service import store_activity_media

        mock_activities_service.owns_activity.return_value = True
        storage = MagicMock()
        mock_media_crud.get_activity_media_by_content_hash.return_value = None
        mock_media_crud.create_activity_media.return_value = ActivityMediaRecord(
            id=9, activity_id=1, media_path="1_abc.jpg", media_type=1
        )

        result = store_activity_media(1, 2, "ride.jpg", b"bytes", storage, MagicMock())

        assert result.id == 9
        assert "/activities/1/media/9/file?t=" in result.url
        area, key, data, content_type = storage.save.call_args.args
        assert area == "activity_media"
        assert key.startswith("1_") and key.endswith(".jpg")
        assert data == b"bytes"
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
        existing = ActivityMediaRecord(id=4, activity_id=1, media_path="1_existing.jpg", media_type=1)
        mock_media_crud.get_activity_media_by_content_hash.return_value = existing

        result = store_activity_media(1, 2, "ride.jpg", b"bytes", storage, MagicMock())

        assert result.id == 4
        storage.save.assert_not_called()
        mock_media_crud.create_activity_media.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_rejects_activity_owned_by_another_user(self, mock_activities_service, mock_media_crud):
        from modules.activities.activity_media.service import store_activity_media

        mock_activities_service.owns_activity.return_value = False

        with pytest.raises(core_exceptions.NotFoundError) as exc:
            storage = MagicMock()
            store_activity_media(1, 2, "ride.jpg", b"bytes", storage, MagicMock())

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
            store_activity_media(1, 2, "ride.jpg", b"bytes", storage, MagicMock())

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
        db.commit.side_effect = OperationalError("stmt", {}, Exception("connection lost"))
        mock_media_crud.get_activity_media_by_content_hash.return_value = None

        with pytest.raises(OperationalError):
            store_activity_media(1, 2, "ride.jpg", b"bytes", storage, db)

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
        winner = ActivityMediaRecord(id=4, activity_id=1, media_path="1_winner.jpg", media_type=1)
        # Miss on the pre-check, then find the winner once the insert conflicts.
        mock_media_crud.get_activity_media_by_content_hash.side_effect = [None, winner]
        mock_media_crud.create_activity_media.side_effect = core_exceptions.ConflictError("dup")

        result = store_activity_media(1, 2, "ride.jpg", b"bytes", storage, MagicMock())

        assert result.id == 4
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
        winner = ActivityMediaRecord(id=4, activity_id=1, media_path="1_winner.jpg", media_type=1)

        def lookup(*_args, **_kwargs):
            events.append("lookup")
            return None if events.count("lookup") == 1 else winner

        mock_media_crud.get_activity_media_by_content_hash.side_effect = lookup
        mock_media_crud.create_activity_media.side_effect = core_exceptions.ConflictError("dup")

        result = store_activity_media_bytes(1, "photo.jpg", b"bytes", MagicMock(), db)

        assert result.id == 4
        assert events == ["lookup", "rollback", "lookup"]
        db.commit.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    def test_a_successful_store_commits(self, mock_media_crud):
        from modules.activities.activity_media.contracts import ActivityMediaRecord
        from modules.activities.activity_media.service import store_activity_media_bytes

        db = MagicMock()
        mock_media_crud.get_activity_media_by_content_hash.return_value = None
        mock_media_crud.create_activity_media.return_value = ActivityMediaRecord(
            id=9, activity_id=1, media_path="1_abc.jpg", media_type=1
        )

        store_activity_media_bytes(1, "photo.jpg", b"bytes", MagicMock(), db)

        db.commit.assert_called_once()


class TestStoreActivityMediaBytes:
    """The server-side ingestion counterpart (Strava bulk-export sidecar photos)."""

    @patch(f"{_SVC}.activity_media_crud")
    def test_saves_blob_and_creates_record(self, mock_media_crud):
        from modules.activities.activity_media.contracts import ActivityMediaRecord
        from modules.activities.activity_media.service import store_activity_media_bytes

        storage = MagicMock()
        mock_media_crud.get_activity_media_by_content_hash.return_value = None
        mock_media_crud.create_activity_media.return_value = ActivityMediaRecord(
            id=9, activity_id=1, media_path="1_abc.jpg", media_type=1
        )

        result = store_activity_media_bytes(1, "photo.jpg", b"bytes", storage, MagicMock())

        assert result.id == 9
        area, _key, data, content_type = storage.save.call_args.args
        assert area == "activity_media"
        assert data == b"bytes"
        assert content_type == "image/jpeg"
        assert mock_media_crud.create_activity_media.call_args.kwargs["content_hash"]

    @patch(f"{_SVC}.activity_media_crud")
    def test_re_running_a_bulk_import_does_not_duplicate_the_photo(self, mock_media_crud):
        """A Strava bulk-export re-run must not create a second media row for a
        photo it already imported for this activity."""
        from modules.activities.activity_media.contracts import ActivityMediaRecord
        from modules.activities.activity_media.service import store_activity_media_bytes

        storage = MagicMock()
        existing = ActivityMediaRecord(id=4, activity_id=1, media_path="1_existing.jpg", media_type=1)
        mock_media_crud.get_activity_media_by_content_hash.return_value = existing

        result = store_activity_media_bytes(1, "photo.jpg", b"bytes", storage, MagicMock())

        assert result.id == 4
        storage.save.assert_not_called()
        mock_media_crud.create_activity_media.assert_not_called()


class TestDeleteActivityMedia:
    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_deletes_record_and_blob(self, mock_activities_service, mock_media_crud):
        from modules.activities.activity_media.service import delete_activity_media

        mock_media_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=1, media_path="1_abc.jpg")
        mock_activities_service.owns_activity.return_value = True

        storage = MagicMock()
        delete_activity_media(1, 5, 2, storage, MagicMock())

        mock_media_crud.delete_activity_media.assert_called_once()
        storage.delete.assert_called_once_with("activity_media", "1_abc.jpg")

    @patch(f"{_SVC}.activity_media_crud")
    def test_missing_media_is_404(self, mock_media_crud):
        from modules.activities.activity_media.service import delete_activity_media

        mock_media_crud.get_activity_media_by_id.return_value = None

        with pytest.raises(core_exceptions.NotFoundError) as exc:
            storage = MagicMock()
            delete_activity_media(1, 5, 2, storage, MagicMock())
        assert exc.value.status_code == 404

    @patch(f"{_SVC}.activity_media_crud")
    def test_media_belonging_to_another_activity_is_404(self, mock_media_crud):
        """The media id must match the activity in the route path.

        Now that the route is ``/activities/{activity_id}/media/{media_id}``, a
        media id reached through an unrelated activity's URL must not resolve —
        otherwise the path would claim a relationship the handler never checked.
        """
        from modules.activities.activity_media.service import delete_activity_media

        mock_media_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=99, media_path="/media/x.jpg")

        with pytest.raises(core_exceptions.NotFoundError) as exc:
            storage = MagicMock()
            delete_activity_media(1, 5, 2, storage, MagicMock())

        assert exc.value.status_code == 404
        mock_media_crud.delete_activity_media.assert_not_called()

    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_media_on_another_users_activity_is_404(self, mock_activities_service, mock_media_crud):
        from modules.activities.activity_media.service import delete_activity_media

        mock_media_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=1, media_path="/media/x.jpg")
        mock_activities_service.owns_activity.return_value = False

        with pytest.raises(core_exceptions.NotFoundError) as exc:
            storage = MagicMock()
            delete_activity_media(1, 5, 2, storage, MagicMock())

        assert exc.value.status_code == 404
        # 404 rather than 403 so media ids cannot be probed, and nothing is deleted.
        mock_media_crud.delete_activity_media.assert_not_called()

    @patch(f"{_SVC}.logger")
    @patch(f"{_SVC}.activity_media_crud")
    @patch(f"{_SVC}.activity_integration")
    def test_cleanup_failure_is_logged_not_raised(self, mock_activities_service, mock_media_crud, mock_logger):
        from modules.activities.activity_media.service import delete_activity_media

        mock_media_crud.get_activity_media_by_id.return_value = MagicMock(activity_id=1, media_path="1_abc.jpg")
        mock_activities_service.owns_activity.return_value = True
        storage = MagicMock()
        storage.delete.side_effect = OSError("backend down")

        delete_activity_media(1, 5, 2, storage, MagicMock())

        # The row is still gone; only the blob cleanup failed.
        mock_media_crud.delete_activity_media.assert_called_once()
        mock_logger.warning.assert_called_once()
