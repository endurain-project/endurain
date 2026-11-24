"""The profile photos' storage, on the real database and the platform's storage."""

import io
import os
import time
import types
import uuid
from functools import partial

import jasil.providers as platform_providers
import jasil.runtime as jasil_runtime
import pytest
from fastapi import UploadFile
from PIL import Image

import core.blob_sweep as core_blob_sweep
import core.exceptions as core_exceptions
import core.file_uploads as core_file_uploads
import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.crud as users_crud
import modules.users.users.photo_service as users_photo_service
import modules.users.users.signing as users_signing
from tests._factories.users import audit_rows_of, make_user
from tests._helpers import images

_AREA = "user_images"
_PNG = images.png_with_text()


class _Storage:
    """The platform storage with the failures of an unreachable backend arranged on chosen calls."""

    def __init__(self, storage, *, delete=None, list_keys=None):
        self._storage = storage
        self._failures = {"delete": delete, "list_keys": list_keys}

    def __getattr__(self, name):
        failure = self._failures.get(name)
        if failure is not None:

            def fail(*_args, **_kwargs):
                raise failure

            return fail
        return getattr(self._storage, name)


@pytest.fixture
def storage():
    return jasil_runtime.get_active_platform().storage


@pytest.fixture
def user(db):
    return make_user(db)


def _keys(storage) -> list[str]:
    return sorted(storage.list_keys(_AREA))


def _png_upload(name: str = "me.png"):
    return name, lambda: _PNG


class TestSigning:
    def test_a_token_is_valid_for_the_user_it_was_minted_for(self):
        user_id = uuid.uuid4()

        assert users_signing.verify_user_image_token(user_id, users_signing.sign_user_image_token(user_id)) is True

    def test_a_token_replayed_against_another_user_is_refused(self):
        token = users_signing.sign_user_image_token(uuid.uuid4())

        assert users_signing.verify_user_image_token(uuid.uuid4(), token) is False

    @pytest.mark.parametrize("token", ["made-up", ""])
    def test_a_forged_or_empty_token_is_refused(self, token):
        assert users_signing.verify_user_image_token(uuid.uuid4(), token) is False

    def test_a_token_of_another_blob_kind_does_not_authorize_a_photo(self):
        from modules.activities.activity_media.signing import sign_media_token
        from modules.activities.activity_thumbnail.signing import sign_thumbnail_token

        some_id = uuid.uuid4()

        assert users_signing.verify_user_image_token(some_id, sign_thumbnail_token(some_id)) is False
        assert users_signing.verify_user_image_token(some_id, sign_media_token(some_id)) is False

    def test_a_token_older_than_its_lifetime_is_refused(self, monkeypatch):
        import itsdangerous.timed

        user_id = uuid.uuid4()
        token = users_signing.sign_user_image_token(user_id)
        later = time.time() + 2 * 24 * 60 * 60
        monkeypatch.setattr(itsdangerous.timed, "time", types.SimpleNamespace(time=lambda: later))

        assert users_signing.verify_user_image_token(user_id, token) is False

    def test_a_photo_url_is_addressed_to_the_photo_route_with_a_token_bound_to_the_user(self):
        user_id = uuid.uuid4()

        url = users_signing.user_image_url(f"{user_id}.png", user_id)

        assert url is not None
        assert f"/users/{user_id}/photo?t=" in url
        assert users_signing.verify_user_image_token(user_id, url.split("?t=")[1]) is True

    def test_no_key_or_no_user_means_no_url(self):
        assert users_signing.user_image_url(None, uuid.uuid4()) is None
        assert users_signing.user_image_url("a.png", None) is None


class TestUserReadCarriesTheSignedUrl:
    def test_the_stored_key_is_answered_as_an_address(self, db):
        user = make_user(db)
        users_crud.replace_photo_key(user.id, f"{user.id}.png", db)

        read = users_crud.get_user_by_id(user.id, db)

        assert f"/users/{user.id}/photo?t=" in read.photo_path


class TestStorePhoto:
    def test_the_blob_is_stored_and_the_key_recorded_on_the_row(self, db, user, storage):
        key = users_photo_service.store_photo(user.id, ".png", _PNG, storage, db)

        assert key == f"{user.id}.png"
        assert users_crud.get_photo_key(user.id, db) == key
        assert storage.get(_AREA, key) is not None

    def test_the_stored_photo_has_no_metadata_and_is_capped_at_512_pixels(self, db, user, storage):
        buffer = io.BytesIO()
        Image.new("RGB", (2000, 1000)).save(buffer, "JPEG", exif=images.exif_with_gps())

        key = users_photo_service.store_photo(user.id, ".jpg", buffer.getvalue(), storage, db)

        stored = storage.get(_AREA, key)
        assert not images.has_metadata(stored)
        with Image.open(io.BytesIO(stored)) as image:
            assert image.size == (512, 256)

    def test_a_webp_is_stored_without_its_metadata_as_a_webp(self, db, user, storage):
        key = users_photo_service.store_photo(user.id, ".webp", images.webp_with_exif(), storage, db)

        assert key.endswith(".webp")
        assert not images.has_metadata(storage.get(_AREA, key))

    def test_the_blob_the_row_named_before_is_removed_and_the_new_one_kept(self, db, user, storage):
        users_photo_service.store_photo(user.id, ".jpg", images.jpeg_with_exif(), storage, db)

        users_photo_service.store_photo(user.id, ".png", _PNG, storage, db)

        assert _keys(storage) == [f"{user.id}.png"]

    def test_a_photo_replaced_under_the_same_extension_is_not_removed(self, db, user, storage):
        users_photo_service.store_photo(user.id, ".png", _PNG, storage, db)

        users_photo_service.store_photo(user.id, ".png", images.png_with_text(size=(16, 16)), storage, db)

        assert _keys(storage) == [f"{user.id}.png"]

    def test_a_failed_cleanup_of_the_replaced_blob_does_not_fail_the_upload(self, db, user, storage):
        users_photo_service.store_photo(user.id, ".jpg", images.jpeg_with_exif(), storage, db)
        down = _Storage(storage, delete=platform_providers.StorageBackendUnavailableError("storage down"))

        key = users_photo_service.store_photo(user.id, ".webp", images.webp_with_exif(), down, db)

        assert users_crud.get_photo_key(user.id, db) == key
        assert _keys(storage) == sorted([f"{user.id}.jpg", key])

    def test_an_extension_that_is_not_an_image_stores_nothing(self, db, user, storage):
        with pytest.raises(core_exceptions.UnsupportedMediaTypeError):
            users_photo_service.store_photo(user.id, ".gif", _PNG, storage, db)

        assert _keys(storage) == []
        assert users_crud.get_photo_key(user.id, db) is None

    def test_a_missing_user_stores_nothing(self, db, storage):
        with pytest.raises(core_exceptions.NotFoundError):
            users_photo_service.store_photo(uuid.uuid4(), ".png", _PNG, storage, db)

        assert _keys(storage) == []

    def test_an_administrators_change_records_the_changed_field_and_a_users_own_does_not(self, db, user, storage):
        users_photo_service.store_photo(user.id, ".png", _PNG, storage, db)
        assert audit_rows_of(db, users_audit_actions.USER_UPDATE.id) == []

        users_photo_service.store_photo(user.id, ".png", _PNG, storage, db, audit=True)

        [row] = audit_rows_of(db, users_audit_actions.USER_UPDATE.id)
        assert (row.target_id, row.details["changed_fields"]) == (str(user.id), ["photo_path"])


class TestUploadPhoto:
    def test_the_upload_is_stored_and_says_whether_it_replaced_a_photo(self, db, user, storage):
        name, read = _png_upload()

        assert users_photo_service.upload_photo(user.id, name, read, storage, db) is False
        assert users_photo_service.upload_photo(user.id, name, read, storage, db) is True
        assert _keys(storage) == [f"{user.id}.png"]

    def test_the_extension_picks_the_stored_type_whatever_its_case(self, db, user, storage):
        users_photo_service.upload_photo(user.id, "Me.PNG", lambda: _PNG, storage, db)

        assert _keys(storage) == [f"{user.id}.png"]

    def test_a_missing_user_is_not_found_and_the_upload_is_never_read(self, db, storage):
        read_calls = []

        with pytest.raises(core_exceptions.NotFoundError):
            users_photo_service.upload_photo(uuid.uuid4(), "me.png", lambda: read_calls.append(1) or _PNG, storage, db)

        assert read_calls == []

    @pytest.mark.parametrize("filename", [None, ""])
    def test_an_upload_without_a_filename_is_invalid_and_never_read(self, db, user, storage, filename):
        read_calls = []

        with pytest.raises(core_exceptions.InvalidInputError):
            users_photo_service.upload_photo(user.id, filename, lambda: read_calls.append(1) or _PNG, storage, db)

        assert read_calls == []

    def test_an_extension_that_is_not_an_image_stores_nothing_and_is_never_read(self, db, user, storage):
        read_calls = []

        with pytest.raises(core_exceptions.UnsupportedMediaTypeError):
            users_photo_service.upload_photo(user.id, "me.exe", lambda: read_calls.append(1) or _PNG, storage, db)

        assert (read_calls, _keys(storage)) == ([], [])

    def test_an_upload_the_reader_refuses_stores_nothing(self, db, user, storage):
        def refuse() -> bytes:
            raise core_exceptions.PayloadTooLargeError("too big")

        with pytest.raises(core_exceptions.PayloadTooLargeError):
            users_photo_service.upload_photo(user.id, "me.png", refuse, storage, db)

        assert (_keys(storage), users_crud.get_photo_key(user.id, db)) == ([], None)

    @pytest.mark.parametrize(
        ("name", "data"),
        [("a.gif", images.gif()), ("a.heic", images.heic_like()), ("a.webp", images.gif())],
        ids=["gif", "heic", "gif-as-webp"],
    )
    def test_a_gif_a_heic_and_a_mislabelled_upload_are_refused_by_the_shared_reader(
        self, db, user, storage, name, data
    ):
        upload = UploadFile(io.BytesIO(data), filename=name)

        with pytest.raises(core_exceptions.DomainError) as err:
            users_photo_service.upload_photo(
                user.id,
                upload.filename,
                partial(core_file_uploads.read_validated_upload_sync, upload, kind=core_file_uploads.UploadKind.IMAGE),
                storage,
                db,
            )

        assert err.value.status_code in {400, 415}
        assert _keys(storage) == []


class TestDeletePhoto:
    def test_the_reference_is_cleared_and_the_blob_removed(self, db, user, storage):
        users_photo_service.store_photo(user.id, ".png", _PNG, storage, db)

        users_photo_service.delete_photo(user.id, storage, db)

        assert users_crud.get_photo_key(user.id, db) is None
        assert _keys(storage) == []

    def test_a_storage_failure_after_the_commit_does_not_fail_the_request(self, db, user, storage):
        users_photo_service.store_photo(user.id, ".png", _PNG, storage, db)
        down = _Storage(storage, delete=platform_providers.StorageBackendUnavailableError("storage down"))

        users_photo_service.delete_photo(user.id, down, db)

        assert users_crud.get_photo_key(user.id, db) is None

    def test_an_unexpected_storage_error_propagates(self, db, user, storage):
        users_photo_service.store_photo(user.id, ".png", _PNG, storage, db)

        with pytest.raises(OSError):
            users_photo_service.delete_photo(user.id, _Storage(storage, delete=OSError("disk gone")), db)

    def test_a_missing_user_is_not_found(self, db, storage):
        with pytest.raises(core_exceptions.NotFoundError):
            users_photo_service.delete_photo(uuid.uuid4(), storage, db)

    def test_an_administrators_delete_is_audited_only_when_a_photo_was_cleared(self, db, user, storage):
        users_photo_service.delete_photo(user.id, storage, db, audit=True)
        assert audit_rows_of(db, users_audit_actions.USER_UPDATE.id) == []

        users_photo_service.store_photo(user.id, ".png", _PNG, storage, db)
        users_photo_service.delete_photo(user.id, storage, db, audit=True)

        [row] = audit_rows_of(db, users_audit_actions.USER_UPDATE.id)
        assert row.details["changed_fields"] == ["photo_path"]

    def test_a_users_own_delete_is_not_audited(self, db, user, storage):
        users_photo_service.store_photo(user.id, ".png", _PNG, storage, db)

        users_photo_service.delete_photo(user.id, storage, db)

        assert audit_rows_of(db, users_audit_actions.USER_UPDATE.id) == []


class TestDeletePhotoFiles:
    def test_every_stored_extension_of_the_user_is_deleted_and_nobody_elses(self, user, storage):
        other = uuid.uuid4()
        for key in (f"{user.id}.jpg", f"{user.id}.png", f"{other}.png"):
            storage.save(_AREA, key, b"x", "image/png")

        users_photo_service.delete_photo_files(user.id, storage)

        assert _keys(storage) == [f"{other}.png"]

    def test_a_storage_failure_is_raised_so_the_account_deletion_is_retried(self, user, storage):
        with pytest.raises(OSError):
            users_photo_service.delete_photo_files(user.id, _Storage(storage, list_keys=OSError("storage down")))


class TestReadPhoto:
    def test_the_blob_the_row_names_is_served_with_its_content_type(self, db, user, storage):
        key = users_photo_service.store_photo(user.id, ".png", _PNG, storage, db)
        token = users_signing.sign_user_image_token(user.id)

        data, content_type = users_photo_service.read_photo(user.id, token, storage, db)

        assert (data, content_type) == (storage.get(_AREA, key), "image/png")

    def test_a_blob_left_under_another_extension_is_never_served(self, db, user, storage):
        storage.save(_AREA, f"{user.id}.jpg", b"old", "image/jpeg")
        users_photo_service.store_photo(user.id, ".png", _PNG, storage, db)
        storage.save(_AREA, f"{user.id}.jpg", b"old", "image/jpeg")

        data, _ = users_photo_service.read_photo(user.id, users_signing.sign_user_image_token(user.id), storage, db)

        assert data != b"old"

    def test_an_invalid_token_is_not_found(self, db, user, storage):
        users_photo_service.store_photo(user.id, ".png", _PNG, storage, db)

        with pytest.raises(core_exceptions.NotFoundError):
            users_photo_service.read_photo(user.id, "forged", storage, db)

    def test_a_token_minted_for_another_user_is_not_found(self, db, user, storage):
        users_photo_service.store_photo(user.id, ".png", _PNG, storage, db)

        with pytest.raises(core_exceptions.NotFoundError):
            users_photo_service.read_photo(user.id, users_signing.sign_user_image_token(uuid.uuid4()), storage, db)

    def test_a_user_without_a_photo_is_not_found(self, db, user, storage):
        with pytest.raises(core_exceptions.NotFoundError):
            users_photo_service.read_photo(user.id, users_signing.sign_user_image_token(user.id), storage, db)

    def test_a_row_whose_blob_is_missing_is_not_found(self, db, user, storage):
        users_crud.replace_photo_key(user.id, f"{user.id}.png", db)

        with pytest.raises(core_exceptions.NotFoundError):
            users_photo_service.read_photo(user.id, users_signing.sign_user_image_token(user.id), storage, db)

    def test_a_key_with_an_unknown_extension_is_served_as_a_binary(self, db, user, storage):
        users_crud.replace_photo_key(user.id, f"{user.id}.bin", db)
        storage.save(_AREA, f"{user.id}.bin", b"blob", "application/octet-stream")

        data, content_type = users_photo_service.read_photo(
            user.id, users_signing.sign_user_image_token(user.id), storage, db
        )

        assert (data, content_type) == (b"blob", "application/octet-stream")


class TestSweepUnreferencedPhotos:
    @staticmethod
    def _age(tmp_path, seconds: float) -> None:
        old = time.time() - seconds
        for path in tmp_path.rglob("*"):
            if path.is_file():
                os.utime(path, (old, old))

    def test_only_old_photos_no_user_names_are_removed(self, db, storage, tmp_path):
        named, replaced_owner, other = make_user(db), make_user(db), make_user(db)
        gone = uuid.uuid4()
        users_crud.replace_photo_key(named.id, f"{named.id}.png", db)
        users_crud.replace_photo_key(replaced_owner.id, f"{replaced_owner.id}.png", db)
        for key in (
            f"{named.id}.png",
            f"{replaced_owner.id}.png",
            f"{replaced_owner.id}.jpg",
            f"{gone}.png",
            f"{other.id}.png",
            "notes.txt",
        ):
            storage.save(_AREA, key, b"x", "image/png")
        db.commit()
        self._age(tmp_path, 2 * core_blob_sweep.MIN_AGE_SECONDS)
        storage.save(_AREA, f"{uuid.uuid4()}.png", b"fresh", "image/png")

        removed = users_photo_service.sweep_unreferenced_photos(storage)

        assert removed == 3
        kept = _keys(storage)
        assert f"{named.id}.png" in kept
        assert f"{replaced_owner.id}.png" in kept
        assert "notes.txt" in kept
        assert f"{replaced_owner.id}.jpg" not in kept
        assert f"{gone}.png" not in kept
        assert f"{other.id}.png" not in kept
        assert len(kept) == 4

    def test_a_sweep_that_finds_nothing_removes_nothing(self, storage):
        assert users_photo_service.sweep_unreferenced_photos(storage) == 0
