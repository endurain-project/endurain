"""Each activity storage area names the activity that owns a blob, so the orphan sweep can find it."""

import uuid

import modules.activities.activity_file_storage.files as files
import modules.activities.activity_media.service as media_service
import modules.activities.activity_thumbnail.service as thumbnail_service

ACTIVITY_ID = uuid.UUID("0b1f6f0e-4c1c-4d5e-9a3b-7a2f1d9c8e41")


class TestKeyParsers:
    def test_processed_key_names_its_activity(self):
        assert files.activity_id_of_processed_key(f"processed/{ACTIVITY_ID}.fit") == ACTIVITY_ID

    def test_staged_upload_in_the_same_area_is_not_a_retained_file(self):
        assert files.activity_id_of_processed_key(f"upload_staging/{ACTIVITY_ID}.fit") is None

    def test_processed_key_with_unknown_extension_is_ignored(self):
        assert files.activity_id_of_processed_key(f"processed/{ACTIVITY_ID}.exe") is None

    def test_thumbnail_key(self):
        assert thumbnail_service._activity_id_of_thumbnail_key(f"{ACTIVITY_ID}.webp") == ACTIVITY_ID
        assert thumbnail_service._activity_id_of_thumbnail_key(f"{ACTIVITY_ID}.png") is None
        assert thumbnail_service._activity_id_of_thumbnail_key("x.webp") is None

    def test_media_key(self):
        assert media_service._activity_id_of_media_key(f"{ACTIVITY_ID}_abc.jpg") == ACTIVITY_ID
        assert media_service._activity_id_of_media_key("abc.jpg") is None

    def test_integer_layout_keys_are_not_this_modules_and_are_ignored(self):
        assert files.activity_id_of_processed_key("processed/42.fit") is None
        assert thumbnail_service._activity_id_of_thumbnail_key("42.webp") is None
        assert media_service._activity_id_of_media_key("42_x.jpg") is None

    def test_non_canonical_uuid_spellings_are_ignored(self):
        upper = str(ACTIVITY_ID).upper()
        assert files.activity_id_of_processed_key(f"processed/{upper}.fit") is None
        assert files.activity_id_of_processed_key(f"processed/{ACTIVITY_ID.hex}.fit") is None
        assert thumbnail_service._activity_id_of_thumbnail_key(f"{upper}.webp") is None
        assert thumbnail_service._activity_id_of_thumbnail_key(f"{ACTIVITY_ID.hex}.webp") is None
        assert media_service._activity_id_of_media_key(f"{upper}_x.jpg") is None
