"""The signed-in user's photo flows on the real database and storage."""

import uuid

import pytest

import core.exceptions as core_exceptions
import modules.users.users.constants as users_constants
import modules.users.users.integration_service as users_integration
import modules.users.users_profile.photo_service as photo_service
from tests._factories.profile import png
from tests._factories.users import make_user

_AREA = users_constants.USER_IMAGE_STORAGE_AREA


@pytest.fixture
def storage(_publish_local_platform):
    return _publish_local_platform.storage


class TestSetPhoto:
    def test_the_first_photo_is_stored_and_served_and_a_second_one_replaces_it(self, db, storage):
        user = make_user(db)

        photo, replaced = photo_service.set_photo(user.id, "me.png", lambda: png(60, 8), storage, db)
        again, replaced_again = photo_service.set_photo(user.id, "me.png", lambda: png(120, 8), storage, db)

        assert (replaced, replaced_again) == (False, True)
        assert photo.photo_path == again.photo_path
        assert photo.photo_path is not None
        assert storage.list_keys(_AREA, f"{user.id}.") == [f"{user.id}.png"]
        assert users_integration.require_user(user.id, db).photo_path == again.photo_path

    def test_an_extension_that_is_not_an_image_is_refused_before_the_file_is_read(self, db, storage):
        user = make_user(db)

        def read():
            raise AssertionError("the upload must not be read")

        with pytest.raises(core_exceptions.UnsupportedMediaTypeError):
            photo_service.set_photo(user.id, "me.exe", read, storage, db)

        assert users_integration.require_user(user.id, db).photo_path is None

    def test_an_upload_without_a_name_is_refused(self, db, storage):
        user = make_user(db)

        with pytest.raises(core_exceptions.InvalidInputError):
            photo_service.set_photo(user.id, None, lambda: png(), storage, db)

    def test_an_unknown_user_is_not_found(self, db, storage):
        with pytest.raises(core_exceptions.NotFoundError):
            photo_service.set_photo(uuid.uuid4(), "me.png", lambda: png(), storage, db)


class TestDeletePhoto:
    def test_the_reference_and_the_stored_blob_go(self, db, storage):
        user = make_user(db)
        photo_service.set_photo(user.id, "me.png", lambda: png(60, 8), storage, db)

        photo_service.delete_photo(user.id, storage, db)

        assert users_integration.require_user(user.id, db).photo_path is None
        assert storage.list_keys(_AREA, f"{user.id}.") == []

    def test_a_user_without_a_photo_is_left_as_they_are(self, db, storage):
        user = make_user(db)

        photo_service.delete_photo(user.id, storage, db)

        assert users_integration.require_user(user.id, db).photo_path is None

    def test_an_unknown_user_is_not_found(self, db, storage):
        with pytest.raises(core_exceptions.NotFoundError):
            photo_service.delete_photo(uuid.uuid4(), storage, db)
