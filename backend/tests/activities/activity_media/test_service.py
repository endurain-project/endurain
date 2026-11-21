"""Activity media on the real database and the platform's local storage: stored, listed, served and swept."""

import os
import re
import uuid
from datetime import UTC, datetime, timedelta

import jasil.providers as platform_providers
import jasil.runtime as platform_runtime
import pytest
from jasil.backends.storage_local import LocalStorage

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import modules.activities.activity_media.constants as media_constants
import modules.activities.activity_media.crud as media_crud
import modules.activities.activity_media.service as media_service
import modules.activities.activity_media.signing as media_signing
from tests._factories.activities import make_activity, make_stored_media
from tests._factories.users import make_user
from tests._helpers import images

_AREA = media_constants.MEDIA_STORAGE_AREA
_KEY = re.compile(r"[0-9a-f-]{36}_[0-9a-f]{32}\.(jpg|jpeg|png|webp)")


class UnavailableStorage(LocalStorage):
    """Local storage whose deletes fail, as an object store that is down does."""

    def delete(self, area: str, key: str) -> None:
        raise platform_providers.StorageBackendUnavailableError("storage down")


@pytest.fixture
def storage():
    return platform_runtime.get_active_platform().storage


@pytest.fixture
def owner(db):
    return make_user(db)


@pytest.fixture
def activity(db, owner):
    return make_activity(db, owner.id)


class RacingStorage(LocalStorage):
    """Local storage that lets a competing request commit its row between this request's check and its insert."""

    def __init__(self, *args, competitor, **kwargs):
        super().__init__(*args, **kwargs)
        self._competitor = competitor

    def save(self, area: str, key: str, data: bytes, *args, **kwargs):
        self._competitor(key)
        return super().save(area, key, data, *args, **kwargs)


class FlakyStorage(LocalStorage):
    """Local storage whose reads fail for one key and find nothing for another."""

    def get(self, area: str, key: str):
        if "unreadable" in key:
            raise platform_providers.StorageBackendUnavailableError("storage down")
        if "vanished" in key:
            return None
        return super().get(area, key)


@pytest.fixture
def plain_storage(tmp_path):
    """Local storage that keeps each blob under its own name, so a test can age one on disk."""
    return LocalStorage(str(tmp_path / "plain"), plain_areas=frozenset({_AREA}))


class TestStoreUpload:
    def test_an_image_is_stored_without_its_metadata_under_a_server_made_key(self, db, owner, activity, storage):
        original = images.jpeg_with_exif()

        read = media_service.store_activity_media(activity.id, owner.id, "holiday.JPG", lambda: original, storage, db)

        [record] = media_crud.get_media_for_activity(activity.id, db)
        assert _KEY.fullmatch(record.media_path) and record.media_path.startswith(f"{activity.id}_")
        assert record.content_hash == core_hashing.sha256_hex(original)
        stored = storage.get(_AREA, record.media_path)
        assert stored is not None and not images.has_metadata(stored) and images.has_metadata(original)
        assert (read.id, read.activity_id) == (record.id, activity.id)
        assert media_signing.verify_media_token(read.id, read.url.partition("?t=")[2])

    @pytest.mark.parametrize(
        ("name", "data"),
        [("a.png", images.png_with_text()), ("a.jpeg", images.jpeg_with_exif()), ("a.webp", images.webp_with_exif())],
    )
    def test_every_accepted_format_is_stored_stripped_under_its_extension(
        self, db, owner, activity, storage, name, data
    ):
        media_service.store_activity_media(activity.id, owner.id, name, lambda: data, storage, db)

        [record] = media_crud.get_media_for_activity(activity.id, db)
        assert record.media_path.endswith(os.path.splitext(name)[1])
        assert not images.has_metadata(storage.get(_AREA, record.media_path))

    def test_the_same_bytes_twice_store_one_photo_and_one_blob(self, db, owner, activity, storage):
        data = images.jpeg_with_exif()

        first = media_service.store_activity_media(activity.id, owner.id, "a.jpg", lambda: data, storage, db)
        second = media_service.store_activity_media(activity.id, owner.id, "b.jpg", lambda: data, storage, db)

        assert first.id == second.id
        assert media_crud.count_media_for_activity(activity.id, db) == 1
        assert len(list(storage.list_keys(_AREA, f"{activity.id}_"))) == 1

    def test_the_same_bytes_on_two_activities_are_two_photos(self, db, owner, activity, storage):
        other = make_activity(db, owner.id, start_time=activity.start_time + timedelta(days=1))
        data = images.png_with_text()

        a = media_service.store_activity_media(activity.id, owner.id, "a.png", lambda: data, storage, db)
        b = media_service.store_activity_media(other.id, owner.id, "a.png", lambda: data, storage, db)

        assert a.id != b.id

    def test_an_activity_that_is_not_the_callers_reads_no_upload_and_stores_nothing(self, db, activity, storage):
        stranger = make_user(db)

        def read_upload() -> bytes:
            raise AssertionError("the upload was read")

        with pytest.raises(core_exceptions.NotFoundError):
            media_service.store_activity_media(activity.id, stranger.id, "a.jpg", read_upload, storage, db)

        assert media_crud.count_media_for_activity(activity.id, db) == 0

    @pytest.mark.parametrize("name", ["a.gif", "a.heic", "a", None, "a.JPG.exe", "a.svg"])
    def test_a_name_without_an_accepted_extension_is_refused_and_stores_nothing(
        self, db, owner, activity, storage, name
    ):
        with pytest.raises(core_exceptions.UnsupportedMediaTypeError):
            media_service.store_activity_media(activity.id, owner.id, name, images.jpeg_with_exif, storage, db)

        assert list(storage.list_keys(_AREA, f"{activity.id}_")) == []

    def test_a_directory_in_the_name_never_reaches_the_key(self, db, owner, activity, storage):
        media_service.store_activity_media(
            activity.id, owner.id, "../../etc/passwd.jpg", images.jpeg_with_exif, storage, db
        )

        [key] = storage.list_keys(_AREA, f"{activity.id}_")
        assert _KEY.fullmatch(key)

    def test_bytes_that_are_not_an_image_store_no_row_and_no_blob(self, db, owner, activity, storage):
        with pytest.raises(core_exceptions.InvalidInputError):
            media_service.store_activity_media(activity.id, owner.id, "a.jpg", lambda: b"not an image", storage, db)

        assert media_crud.count_media_for_activity(activity.id, db) == 0
        assert list(storage.list_keys(_AREA, f"{activity.id}_")) == []

    def test_a_validation_failure_of_the_upload_is_raised_as_it_is(self, db, owner, activity, storage):
        def too_big() -> bytes:
            raise core_exceptions.PayloadTooLargeError("too big")

        with pytest.raises(core_exceptions.PayloadTooLargeError):
            media_service.store_activity_media(activity.id, owner.id, "a.jpg", too_big, storage, db)


class TestStoreBytes:
    def test_server_side_bytes_are_stored_for_an_activity_without_an_ownership_check(self, db, activity, storage):
        record = media_service.store_activity_media_bytes(
            activity.id, "sidecar.png", images.png_with_text(), storage, db
        )

        assert storage.get(_AREA, record.media_path) is not None
        assert record.content_hash == core_hashing.sha256_hex(images.png_with_text())

    def test_a_bulk_import_re_run_does_not_duplicate_the_photo(self, db, activity, storage):
        data = images.png_with_text()

        first = media_service.store_activity_media_bytes(activity.id, "a.png", data, storage, db)
        again = media_service.store_activity_media_bytes(activity.id, "a.png", data, storage, db)

        assert again.id == first.id
        assert media_crud.count_media_for_activity(activity.id, db) == 1

    def test_the_blob_is_removed_when_its_row_cannot_be_recorded(self, db, activity, storage, monkeypatch):
        def refuse(*args, **kwargs):
            raise core_exceptions.ConflictError("duplicate")

        monkeypatch.setattr(media_crud, "create_activity_media", refuse)

        with pytest.raises(core_exceptions.ConflictError):
            media_service.store_activity_media_bytes(activity.id, "a.png", images.png_with_text(), storage, db)

        assert list(storage.list_keys(_AREA, f"{activity.id}_")) == []


class TestStoreRaces:
    """Two requests storing the same photo at once: the unique keys decide, and the loser answers the winner."""

    @pytest.fixture
    def committed_activity(self, committed_sessions):
        with committed_sessions() as db:
            activity = make_activity(db, make_user(db).id)
            db.commit()
        return activity

    def _racing(self, committed_sessions, tmp_path, activity, *, content_hash):
        def competitor(key: str) -> None:
            with committed_sessions() as other:
                media_crud.create_activity_media(
                    activity.id, f"{activity.id}_winner.png" if content_hash else key, other, content_hash=content_hash
                )
                other.commit()

        return RacingStorage(str(tmp_path / "race"), plain_areas=frozenset({_AREA}), competitor=competitor)

    def test_the_loser_of_a_race_on_the_same_bytes_answers_the_winner_and_leaves_no_blob(
        self, committed_sessions, committed_activity, tmp_path
    ):
        data = images.png_with_text()
        racing = self._racing(
            committed_sessions, tmp_path, committed_activity, content_hash=core_hashing.sha256_hex(data)
        )

        with committed_sessions() as db:
            answered = media_service.store_activity_media_bytes(committed_activity.id, "a.png", data, racing, db)

        assert answered.media_path == f"{committed_activity.id}_winner.png"
        assert list(racing.list_keys(_AREA, f"{committed_activity.id}_")) == []
        with committed_sessions() as db:
            assert media_crud.count_media_for_activity(committed_activity.id, db) == 1

    def test_a_clash_that_is_not_a_content_duplicate_is_a_conflict_and_leaves_no_blob(
        self, committed_sessions, committed_activity, tmp_path
    ):
        racing = self._racing(committed_sessions, tmp_path, committed_activity, content_hash=None)

        with committed_sessions() as db, pytest.raises(core_exceptions.ConflictError):
            media_service.store_activity_media_bytes(committed_activity.id, "a.png", images.png_with_text(), racing, db)

        assert list(racing.list_keys(_AREA, f"{committed_activity.id}_")) == []

    def test_a_blob_that_cannot_be_removed_after_a_failed_store_is_only_logged(
        self, db, activity, tmp_path, monkeypatch
    ):
        down = UnavailableStorage(str(tmp_path / "down"), plain_areas=frozenset({_AREA}))

        def refuse(*args, **kwargs):
            raise core_exceptions.NotFoundError("gone")

        monkeypatch.setattr(media_crud, "create_activity_media", refuse)

        with pytest.raises(core_exceptions.NotFoundError):
            media_service.store_activity_media_bytes(activity.id, "a.png", images.png_with_text(), down, db)


class TestList:
    def test_the_owner_lists_the_photos_oldest_first_with_a_signed_url_each(self, db, owner, activity):
        first = make_stored_media(db, activity, images.png_with_text(), "a.png")
        second = make_stored_media(db, activity, images.jpeg_with_exif(), "b.jpg")

        page = media_service.list_activity_media(activity.id, owner.id, db)

        assert [item.id for item in page.items] == [first.id, second.id]
        assert page.total == 2
        for item in page.items:
            assert media_signing.verify_media_token(item.id, item.url.partition("?t=")[2])

    def test_a_page_holds_its_slice_and_names_the_next_one(self, db, owner, activity):
        for name, data in (("a.png", images.png_with_text()), ("b.jpg", images.jpeg_with_exif())):
            make_stored_media(db, activity, data, name)

        page = media_service.list_activity_media(activity.id, owner.id, db, page_number=1, num_records=1)

        assert (len(page.items), page.total, page.next) == (1, 2, 2)

    def test_a_stranger_gets_the_page_of_an_activity_that_does_not_exist(self, db, activity):
        make_stored_media(db, activity, images.png_with_text(), "a.png")

        refused = media_service.list_activity_media(activity.id, make_user(db).id, db)
        missing = media_service.list_activity_media(uuid.uuid4(), make_user(db).id, db)

        assert refused.model_dump() == missing.model_dump()
        assert refused.total == 0

    def test_the_media_of_several_activities_is_listed_by_activity(self, db, owner, activity):
        other = make_activity(db, owner.id, start_time=activity.start_time + timedelta(days=1))
        make_stored_media(db, activity, images.png_with_text(), "a.png")
        bare = make_activity(db, owner.id, start_time=activity.start_time + timedelta(days=2))

        listed = media_service.list_media_for_activities([activity.id, other.id, bare.id], db)

        assert set(listed) == {activity.id}
        assert len(listed[activity.id]) == 1


class TestDelete:
    def test_the_row_and_the_blob_go_together_and_the_owner_is_the_only_one_who_may(self, db, owner, activity, storage):
        record = make_stored_media(db, activity, images.png_with_text(), "a.png")

        with pytest.raises(core_exceptions.NotFoundError):
            media_service.delete_activity_media(activity.id, record.id, make_user(db).id, storage, db)
        assert storage.exists(_AREA, record.media_path)

        media_service.delete_activity_media(activity.id, record.id, owner.id, storage, db)

        assert media_crud.get_activity_media_by_id(record.id, db) is None
        assert not storage.exists(_AREA, record.media_path)

    def test_a_missing_media_id_is_not_found(self, db, owner, activity, storage):
        with pytest.raises(core_exceptions.NotFoundError):
            media_service.delete_activity_media(activity.id, uuid.uuid4(), owner.id, storage, db)

    def test_media_reached_through_another_of_the_owners_activities_is_not_found_and_stays(
        self, db, owner, activity, storage
    ):
        other = make_activity(db, owner.id, start_time=activity.start_time + timedelta(days=1))
        record = make_stored_media(db, activity, images.png_with_text(), "a.png")

        with pytest.raises(core_exceptions.NotFoundError):
            media_service.delete_activity_media(other.id, record.id, owner.id, storage, db)

        assert media_crud.get_activity_media_by_id(record.id, db) is not None
        assert storage.exists(_AREA, record.media_path)

    def test_a_storage_that_is_down_leaves_the_blob_but_the_row_is_still_deleted(self, db, owner, activity, tmp_path):
        down = UnavailableStorage(str(tmp_path / "down"), plain_areas=frozenset({_AREA}))
        record = media_service.store_activity_media_bytes(activity.id, "a.png", images.png_with_text(), down, db)

        media_service.delete_activity_media(activity.id, record.id, owner.id, down, db)

        assert media_crud.get_activity_media_by_id(record.id, db) is None
        assert down.exists(_AREA, record.media_path)


class TestReadBlob:
    def test_a_valid_token_serves_the_blob_with_the_type_of_its_extension(self, db, activity, storage):
        record = make_stored_media(db, activity, images.png_with_text(), "a.png")
        token = media_signing.sign_media_token(record.id)

        data, content_type = media_service.read_activity_media_blob(activity.id, record.id, token, storage, db)

        assert (data, content_type) == (storage.get(_AREA, record.media_path), "image/png")

    def test_a_forged_token_is_refused_as_not_found(self, db, activity, storage):
        record = make_stored_media(db, activity, images.png_with_text(), "a.png")

        with pytest.raises(core_exceptions.AccessConcealedError):
            media_service.read_activity_media_blob(activity.id, record.id, "forged", storage, db)

    def test_a_token_minted_for_another_photo_is_refused(self, db, activity, storage):
        record = make_stored_media(db, activity, images.png_with_text(), "a.png")
        other = make_stored_media(db, activity, images.jpeg_with_exif(), "b.jpg")

        with pytest.raises(core_exceptions.AccessConcealedError):
            media_service.read_activity_media_blob(
                activity.id, record.id, media_signing.sign_media_token(other.id), storage, db
            )

    def test_a_token_replayed_under_another_activity_is_not_found(self, db, owner, activity, storage):
        other = make_activity(db, owner.id, start_time=activity.start_time + timedelta(days=1))
        record = make_stored_media(db, activity, images.png_with_text(), "a.png")

        with pytest.raises(core_exceptions.NotFoundError):
            media_service.read_activity_media_blob(
                other.id, record.id, media_signing.sign_media_token(record.id), storage, db
            )

    def test_a_row_whose_blob_is_gone_is_not_found(self, db, activity, storage):
        record = make_stored_media(db, activity, images.png_with_text(), "a.png")
        storage.delete(_AREA, record.media_path)

        with pytest.raises(core_exceptions.NotFoundError):
            media_service.read_activity_media_blob(
                activity.id, record.id, media_signing.sign_media_token(record.id), storage, db
            )

    def test_a_key_stored_under_a_no_longer_accepted_extension_is_served_as_a_download(self, db, activity, storage):
        record = media_crud.create_activity_media(activity.id, f"{activity.id}_old.gif", db)
        storage.save(_AREA, record.media_path, images.gif())

        _, content_type = media_service.read_activity_media_blob(
            activity.id, record.id, media_signing.sign_media_token(record.id), storage, db
        )

        assert content_type == "application/octet-stream"


class TestCleanup:
    def test_the_blobs_of_a_deleted_activity_go_and_another_activitys_stay(self, db, owner, activity, storage):
        other = make_activity(db, owner.id, start_time=activity.start_time + timedelta(days=1))
        mine = make_stored_media(db, activity, images.png_with_text(), "a.png")
        theirs = make_stored_media(db, other, images.png_with_text(), "a.png")

        removed = media_service.delete_media_files_for_activity(activity.id, storage)

        assert removed == 1
        assert not storage.exists(_AREA, mine.media_path) and storage.exists(_AREA, theirs.media_path)
        assert media_service.delete_media_files_for_activity(activity.id, storage) == 0

    def test_a_storage_failure_propagates_so_the_runner_retries(self, db, activity, tmp_path):
        down = UnavailableStorage(str(tmp_path / "down"), plain_areas=frozenset({_AREA}))
        media_service.store_activity_media_bytes(activity.id, "a.png", images.png_with_text(), down, db)

        with pytest.raises(platform_providers.StorageBackendUnavailableError):
            media_service.delete_media_files_for_activity(activity.id, down)

    def test_the_blobs_of_an_activity_are_listed_for_the_export_and_a_missing_blob_is_skipped(
        self, db, activity, storage
    ):
        kept = make_stored_media(db, activity, images.png_with_text(), "a.png")
        storage.save(_AREA, f"{activity.id}_vanishing.png", b"x")

        blobs = media_service.list_media_blobs(activity.id, storage)

        assert (kept.media_path, storage.get(_AREA, kept.media_path)) in blobs
        assert len(blobs) == 2

    def test_a_blob_that_cannot_be_read_or_has_vanished_is_skipped_from_the_export(self, activity, tmp_path):
        flaky = FlakyStorage(str(tmp_path / "flaky"), plain_areas=frozenset({_AREA}))
        for name in ("ok", "unreadable", "vanished"):
            flaky.save(_AREA, f"{activity.id}_{name}.png", b"x")

        blobs = media_service.list_media_blobs(activity.id, flaky)

        assert [key for key, _ in blobs] == [f"{activity.id}_ok.png"]

    def test_restoring_a_blob_stores_it_under_the_new_activitys_key(self, activity, storage):
        key = media_service.store_media_blob(activity.id, "photo", ".png", b"bytes", storage)

        assert (key, storage.get(_AREA, key)) == (f"{activity.id}_photo.png", b"bytes")


class TestRekey:
    def test_an_archived_key_is_re_addressed_to_the_restored_activity(self):
        archived, new = uuid.uuid4(), uuid.uuid4()

        assert media_service.rekey_media_path(f"{archived}_a.jpg", archived, new) == f"{new}_a.jpg"

    @pytest.mark.parametrize("suffix", ["../escape.jpg", "dir/a.jpg", "dir\\a.jpg", ""])
    def test_a_suffix_that_is_not_a_flat_file_name_is_refused(self, suffix):
        archived = uuid.uuid4()

        assert media_service.rekey_media_path(f"{archived}_{suffix}", archived, uuid.uuid4()) is None

    def test_a_key_of_another_activity_is_refused(self):
        assert media_service.rekey_media_path(f"{uuid.uuid4()}_a.jpg", uuid.uuid4(), uuid.uuid4()) is None


class TestSweep:
    @staticmethod
    def _age(tmp_path, key: str) -> None:
        old = (datetime.now(UTC) - timedelta(days=2)).timestamp()
        os.utime(tmp_path / "plain" / _AREA / key, (old, old))

    def test_an_old_blob_of_a_deleted_activity_is_swept_and_a_young_one_is_kept(self, tmp_path, plain_storage):
        gone = uuid.uuid4()
        plain_storage.save(_AREA, f"{gone}_old.png", b"x")
        plain_storage.save(_AREA, f"{gone}_young.png", b"x")
        self._age(tmp_path, f"{gone}_old.png")

        removed = media_service.sweep_orphaned_media(plain_storage)

        assert removed == 1
        assert not plain_storage.exists(_AREA, f"{gone}_old.png")
        assert plain_storage.exists(_AREA, f"{gone}_young.png")

    def test_an_old_blob_no_row_names_is_swept_and_one_a_row_names_is_kept(self, db, activity, tmp_path, plain_storage):
        named = media_service.store_activity_media_bytes(
            activity.id, "a.png", images.png_with_text(), plain_storage, db
        )
        stray = f"{activity.id}_stray.png"
        plain_storage.save(_AREA, stray, b"x")
        self._age(tmp_path, stray)
        self._age(tmp_path, named.media_path)

        removed = media_service.sweep_orphaned_media(plain_storage)

        assert removed == 1
        assert not plain_storage.exists(_AREA, stray)
        assert plain_storage.exists(_AREA, named.media_path)

    def test_a_key_outside_the_uuid_layout_is_left_alone_by_the_activity_sweep_and_swept_when_no_row_names_it(
        self, tmp_path, plain_storage
    ):
        plain_storage.save(_AREA, "not-a-media-key.png", b"x")
        self._age(tmp_path, "not-a-media-key.png")

        assert media_service.sweep_orphaned_media(plain_storage) == 1
        assert not plain_storage.exists(_AREA, "not-a-media-key.png")
